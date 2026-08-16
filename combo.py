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

# ---------------- 卖点语义聚类（自动，无产品知识） ----------------
#
# 为什么需要：一个产品的多个脚本版本里，几乎每个卖点都有近义孪生
# （「湿抹布分开挂，周围更容易通风」vs「湿物分开悬空，不再全挤成一团」）。
# 不按语义去重，实测 21/39 条成品里有多个卖点在讲同一件事，
# #10 #20 甚至三个卖点都在讲接水【实测】。
#
# 为什么必须自动：手工映射表只对建表的那个产品有效，换文件夹后
# 所有组落进「自成一类」的兜底分支 —— 不报错、静默退化成完全不去重，
# 看起来在工作其实没有，比不做更糟（用户 2026-08-15 否掉了手工表）。
#
# 怎么做到无产品知识：中文短文本不分词，直接取汉字二字组比重叠度。
# 停用词也不写死 —— 出现在超过 DF_MAX 比例文档里的二字组自动丢掉，
# 「一个」「可以」这类自然被滤掉，换产品自动适配。

# 相似度阈值。**越低越容易合并**（低 = 松 = 去重更狠）。
# 用户 2026-08-15 先定 0.10（紧），实测下来紧阈值把大主题拆成子簇、
# 只消掉「三连」留下大量「成对」，当天改用 0.05（松）。
#
# 20 个 seed 实测，判重基准用人工分的 9 类：
#   关闭去重  重复 30.8/39  三连 4.8  —
#   0.10 紧   重复 18.1/39  三连 0.9  跨类误并 0 对
#   0.05 松   重复 13.8/39  三连 0.2  跨类误并 12 对   ← 当前
# 「误并」的基准是人手画的类边界，本身也不是真理，所以 12 对可接受。
SIM_THRESHOLD = 0.05
DF_MAX = 0.34            # 文档频率超过这个比例的二字组视为停用词


def char_bigrams(text):
    """汉字二字组。只留汉字，标点数字英文都丢 —— 它们不携带语义。"""
    han = [c for c in text if "一" <= c <= "鿿"]
    return {"".join(han[i:i + 2]) for i in range(len(han) - 1)}


def auto_cluster(texts, threshold=SIM_THRESHOLD, df_max=DF_MAX):
    """把 {键: 文本} 聚成语义簇，返回 {键: 簇号}。

    Dice 相似度 + 平均连接层次聚类。平均连接而非单连接：
    单连接会「链式串珠」—— A 像 B、B 像 C 就把 A 和 C 拉进同一簇，
    即使 A 和 C 毫不相干，短文本上很容易失控。
    """
    keys = [k for k in texts if texts[k].strip()]
    if len(keys) < 2:
        return {k: i for i, k in enumerate(texts)}

    bg = {k: char_bigrams(texts[k]) for k in keys}
    df = {}
    for s in bg.values():
        for b in s:
            df[b] = df.get(b, 0) + 1
    stop = {b for b, c in df.items() if c > df_max * len(keys)}
    bg = {k: s - stop for k, s in bg.items()}

    def sim(a, b):
        x, y = bg[a], bg[b]
        return 2 * len(x & y) / (len(x) + len(y)) if x or y else 0.0

    clusters = [[k] for k in keys]
    while len(clusters) > 1:
        best, bi, bj = threshold, -1, -1
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                s = sum(sim(a, b) for a in clusters[i] for b in clusters[j])
                s /= len(clusters[i]) * len(clusters[j])
                if s > best:
                    best, bi, bj = s, i, j
        if bi < 0:
            break
        clusters[bi] += clusters[bj]
        clusters.pop(bj)

    out = {k: i for i, c in enumerate(clusters) for k in c}
    # 无文本的（幻觉闸门拦下的静音片）各自成簇。它们不产生听觉重复，
    # 单独处理比硬塞进某个簇更安全。
    n = len(clusters)
    for k in texts:
        if k not in out:
            out[k] = n
            n += 1
    return out


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


def theme_of(group, theme_map):
    """一个变体组属于哪个语义簇。

    查不到就自成一类 —— 未分类的组各自独立，
    既不会挡住抽样，也不会跟别的组抢同一个主题名额。
    """
    lab = group[0].label
    t = theme_map.get(lab)
    return f"__{lab}__" if t is None else t


def inclusion_probs(counts, k):
    """每个主题的目标入选概率：与成员数成正比，截顶到 1 后余额分给其余。

    ⚠ 不能直接拿成员数当权重做逐次加权抽取 —— 那样得到的**入选概率并不
    与权重成正比**（顺序抽取时权重会随已抽走的主题重新归一）。实测按成员数
    逐次加权，`7/稳定承重` 仍有 11 次曝光，期望只有 5.9【实测】。
    要让「片段级曝光均匀」，得直接把入选概率定成 ∝ 成员数。

    截顶是必要的：9 个主题抽 5 个，成员最多的「接水沥水底盘」(7/33)
    按比例要 5x7/33 = 1.06 > 1，物理上不可能，只能定成 1（每条必上），
    余额再按比例分给剩下的主题。
    """
    n = len(counts)
    pi = [0.0] * n
    free = list(range(n))
    budget = k
    while free:
        total = sum(counts[i] for i in free)
        scaled = {i: budget * counts[i] / total for i in free}
        over = [i for i in free if scaled[i] >= 1.0]
        if not over:
            for i in free:
                pi[i] = scaled[i]
            break
        for i in over:
            pi[i] = 1.0
            budget -= 1
        free = [i for i in free if i not in over]
    return pi


def pick_themed_groups(rng, groups, count, theme_map):
    """抽 count 个变体组，同一主题不重复出现。

    **按成员数加权**（用户 2026-08-15 决定）。不加权的话
    `7/稳定承重`、`7/清洁的设计` 这种独占单成员主题的片段，主题一被抽中
    就必上（组内只有它），曝光从 5.9 飙到约 21 次 —— 等于把「语义重复」
    换成「曝光失衡」。

    做法：先算目标入选概率（见 `inclusion_probs`），再用 Madow 系统抽样
    实现它 —— 把各主题的概率首尾相接铺成一条长 count 的数轴，随机取一个
    起点 u∈[0,1)，命中 u, u+1, ... u+count-1 落进的那些主题。
    这样恰好抽满 count 个、每个主题的入选概率精确等于目标值，
    且因为每段宽度 ≤1，同一主题不可能被命中两次。

    主题数不够 count 时，剩下的名额从未用过的组里补 ——
    此时同主题会重复，但这是素材本身不够分，不该直接报错
    （界面上 points 最大能填 20，主题只有 9 个）。
    """
    by_theme = {}
    for g in groups:
        by_theme.setdefault(theme_of(g, theme_map), []).append(g)
    themes = list(by_theme)

    def fill(picked):
        """名额没抽满时从未用过的组里补齐。"""
        if len(picked) < count:
            used = {id(g) for g in picked}
            rest = [g for g in groups if id(g) not in used]
            picked.extend(rng.sample(rest, min(count - len(picked), len(rest))))
        return picked

    if count >= len(themes):
        return fill([rng.choice(by_theme[t]) for t in themes])

    pi = inclusion_probs([len(by_theme[t]) for t in themes], count)
    order = list(range(len(themes)))
    rng.shuffle(order)   # 打乱后再铺，避免表里相邻的主题总是同进同出
    u = rng.random()
    picked, cum, j = [], 0.0, 0
    for i in order:
        cum += pi[i]
        if j < count and u + j < cum:
            picked.append(rng.choice(by_theme[themes[i]]))
            j += 1
    return fill(picked)


def build_combos(pools, point_count=DEFAULT_POINT_COUNT,
                 hook_limit=HOOK_USE_LIMIT, seed=None, theme_map=None):
    """生成全部组合方案。

    钩子按 hook_limit 次配额消耗，配额用尽即废弃，
    所以总条数 = 钩子变体组数 x hook_limit。
    卖点按「变体组」抽样，保证同一素材的两个变体不会同时进一条视频。
    给了 theme_map 还会按语义簇去重，保证一条里不会有两个卖点讲同一件事。
    仍不跨条去重（用户 2026-08-14 确认）—— 只管一条之内。

    theme_map: label -> 簇号，由 `auto_cluster()` 算出（调用方负责，
               因为读 ASR 文本是 IO，本模块不碰）。
               传 None 或 {} 则每组自成一类 = 只去变体不去语义。
    """
    theme_map = theme_map or {}
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
                points=[rng.choice(g) for g in pick_themed_groups(
                    rng, point_groups, point_count, theme_map)],
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
