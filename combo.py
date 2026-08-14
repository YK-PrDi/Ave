"""分镜解析 + 排列组合抽样。

不依赖剪映、不依赖任何云端功能，纯本地逻辑，可独立测试。

组合规则（用户 2026-08-14 确认）：
  - 跨文件夹混池：所有小文件夹的钩子/卖点/结尾各自汇总成三个池
  - 每条成品 = 1 个钩子 + N 个卖点（默认 5，可配）+ 1 个结尾
  - 每个钩子用满 3 次即废弃 → 成品总数 = 钩子数 x 3
  - 片段内顺序：钩子 → 卖点 → 结尾
"""

import os
import random
import re
from dataclasses import dataclass, field

# 角色前缀 -> 归一化角色名。顺序有意义：先匹配长的。
ROLE_PATTERNS = [
    ("钩子", "hook"),
    ("卖点", "point"),
    ("结尾促单", "ending"),
    ("结尾", "ending"),
]

VIDEO_EXT = {".mp4", ".mov", ".mkv", ".avi", ".m4v"}

# 文件名形如：钩子前期-从容秩序-1.mp4 / 卖点3-通风悬挂-1.mp4 / 钩子-2.mp4
# 索引号（卖点3 的 3）和变体号（-1 结尾）都可能缺失
NAME_RE = re.compile(
    r"^(?P<role>钩子|卖点|结尾促单|结尾)"
    r"(?P<phase>前期|后期)?"
    r"(?P<index>\d+)?"
    r"(?:-(?P<desc>.*?))?"
    r"(?:-(?P<variant>\d+))?$"
)


@dataclass
class Clip:
    path: str
    folder: str          # 所属小分镜文件夹名，用于将来按文件夹约束
    role: str            # hook / point / ending
    phase: str = ""      # 前期 / 后期 / ""
    index: int = -1      # 卖点序号，缺失为 -1
    desc: str = ""
    variant: int = 1

    @property
    def name(self):
        return os.path.basename(self.path)

    @property
    def group_key(self):
        """同一素材的不同变体（-1/-2）归为一组。

        抽样时按组抽、组内再随机挑一个变体，
        避免「集中收纳次卖点-1」和「-2」同时出现在一条视频里。

        **内容概括缺失时不归组**（用 path 做键，每个文件自成一组）。
        用户 2026-08-14 确认：`1/钩子-1.mp4` 与 `1/钩子-2.mp4` 是两个不同的钩子，
        不是同一钩子的两个变体。没有内容概括就无从判断二者是否同源，
        按「不同素材」处理更安全 —— 归错组会少产出视频，不归组最多是
        同一条里出现两个相似片段，而缺内容概括本就该在命名阶段修掉。
        """
        if not self.desc:
            return ("__nogroup__", self.path)
        return (self.folder, self.role, self.phase, self.index, self.desc)

    @property
    def label(self):
        return f"{self.folder}/{self.desc or os.path.splitext(self.name)[0]}"


def parse_clip(path, folder):
    """解析单个文件名。无法识别角色返回 None。"""
    stem = os.path.splitext(os.path.basename(path))[0]
    m = NAME_RE.match(stem)
    if not m:
        return None
    role_cn = m.group("role")
    role = next((r for cn, r in ROLE_PATTERNS if cn == role_cn), None)
    if role is None:
        return None
    idx = m.group("index")
    var = m.group("variant")
    desc = (m.group("desc") or "").strip()

    # 「钩子-1.mp4」这类只有一段尾巴的名字，正则会把它当 desc 吃掉。
    # 纯数字的 desc 实际是变体号。
    if var is None and desc.isdigit():
        var, desc = desc, ""

    return Clip(
        path=path,
        folder=folder,
        role=role,
        phase=m.group("phase") or "",
        index=int(idx) if idx else -1,
        desc=desc,
        variant=int(var) if var else 1,
    )


@dataclass
class Pools:
    hooks: list = field(default_factory=list)
    points: list = field(default_factory=list)
    endings: list = field(default_factory=list)
    unparsed: list = field(default_factory=list)

    def summary(self):
        return (f"钩子 {len(self.hooks)} / 卖点 {len(self.points)} / "
                f"结尾 {len(self.endings)}" +
                (f" / 无法解析 {len(self.unparsed)}" if self.unparsed else ""))


def scan_product(product_dir):
    """扫描产品大文件夹，返回三个池。

    结构：产品文件夹 / 小分镜文件夹 / *.mp4
    也容忍 mp4 直接放在产品文件夹根下。
    """
    pools = Pools()

    def take(path, folder):
        if os.path.splitext(path)[1].lower() not in VIDEO_EXT:
            return
        c = parse_clip(path, folder)
        if c is None:
            pools.unparsed.append(path)
        elif c.role == "hook":
            pools.hooks.append(c)
        elif c.role == "point":
            pools.points.append(c)
        else:
            pools.endings.append(c)

    for entry in sorted(os.listdir(product_dir)):
        full = os.path.join(product_dir, entry)
        if os.path.isdir(full):
            for fn in sorted(os.listdir(full)):
                take(os.path.join(full, fn), entry)
        else:
            take(full, "")

    return pools


# ---------------- 组合抽样 ----------------

HOOK_USE_LIMIT = 3       # 每个钩子用满几次就废弃
DEFAULT_POINT_COUNT = 5  # 每条成品用几个卖点


@dataclass
class Combo:
    """一条成品的编排方案。"""
    index: int
    hook: Clip
    points: list
    ending: Clip

    @property
    def clips(self):
        """按最终拼接顺序返回所有片段。"""
        return [self.hook] + list(self.points) + [self.ending]

    def describe(self):
        pts = " + ".join(c.label for c in self.points)
        return (f"#{self.index:02d}  钩子[{self.hook.label}]\n"
                f"      卖点: {pts}\n"
                f"      结尾[{self.ending.label}]")


def group_variants(clips):
    """把变体归组，返回 [[变体1, 变体2], ...]。"""
    groups = {}
    for c in clips:
        groups.setdefault(c.group_key, []).append(c)
    return list(groups.values())


def build_combos(pools, point_count=DEFAULT_POINT_COUNT,
                 hook_limit=HOOK_USE_LIMIT, seed=None):
    """生成全部组合方案。

    钩子按 hook_limit 次配额消耗，配额用尽即废弃，
    所以总条数 = 钩子变体组数 x hook_limit。
    卖点按「变体组」抽样，保证同一素材的两个变体不会同时进一条视频。
    不跨条去重（用户 2026-08-14 确认：先不管语义重复）。
    """
    if not pools.hooks:
        raise ValueError("钩子池为空，无法组合")
    if not pools.endings:
        raise ValueError("结尾池为空，无法组合")

    point_groups = group_variants(pools.points)
    if len(point_groups) < point_count:
        raise ValueError(
            f"卖点只有 {len(point_groups)} 组（去掉变体后），"
            f"不足每条所需的 {point_count} 个")

    rng = random.Random(seed)
    hook_groups = group_variants(pools.hooks)
    combos = []
    n = 0
    for hook_group in hook_groups:
        for _ in range(hook_limit):
            n += 1
            combos.append(Combo(
                index=n,
                hook=rng.choice(hook_group),
                points=[rng.choice(g)
                        for g in rng.sample(point_groups, point_count)],
                ending=rng.choice(rng.choice(group_variants(pools.endings))),
            ))
    return combos


def used_clips(combos):
    """组合里实际用到的所有不重复片段 —— 决定预处理范围。"""
    seen = {}
    for c in combos:
        for clip in c.clips:
            seen[clip.path] = clip
    return list(seen.values())
