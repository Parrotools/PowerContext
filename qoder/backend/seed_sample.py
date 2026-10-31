"""Seed sample learning materials into the knowledge base on first startup."""

import asyncio
import logging
import sys

from app.services import seekdb_service

logger = logging.getLogger(__name__)

SAMPLE_DOCUMENTS = [
    {
        "title": "二叉树基础",
        "content": (
            "二叉树是一种重要的数据结构，每个节点最多有两个子节点：左子节点和右子节点。\n\n"
            "## 二叉树的性质\n\n"
            "1. 第 i 层最多有 2^(i-1) 个节点（i >= 1）\n"
            "2. 深度为 k 的二叉树最多有 2^k - 1 个节点\n"
            "3. 对任意二叉树，叶子节点数 = 度为2的节点数 + 1\n\n"
            "## 特殊二叉树\n\n"
            "- **满二叉树**：每层节点数都达到最大值\n"
            "- **完全二叉树**：除最后一层外，其余层节点数达最大，且最后一层节点靠左排列\n"
            "- **二叉搜索树（BST）**：左子树所有节点值 < 根节点值 < 右子树所有节点值\n\n"
            "## 应用场景\n\n"
            "二叉树广泛应用于编译器语法分析、数据库索引（B+树）、文件系统设计、"
            "表达式求值和 Huffman 编码等领域。"
        ),
        "course": "数据结构",
        "tags": ["二叉树", "数据结构", "树"],
    },
    {
        "title": "二叉树遍历算法",
        "content": (
            "二叉树遍历是访问树中所有节点的基本操作，分为深度优先和广度优先两大类。\n\n"
            "## 深度优先遍历（DFS）\n\n"
            "### 前序遍历（Pre-order）\n访问顺序：根 → 左 → 右\n"
            "应用场景：复制树结构、序列化\n\n"
            "### 中序遍历（In-order）\n访问顺序：左 → 根 → 右\n"
            "应用场景：对 BST 中序遍历可得到有序序列\n\n"
            "### 后序遍历（Post-order）\n访问顺序：左 → 右 → 根\n"
            "应用场景：删除树、计算表达式树的值\n\n"
            "## 广度优先遍历（BFS）\n\n"
            "也叫层序遍历，使用队列实现，逐层从左到右访问节点。\n"
            "应用场景：求最短路径、按层处理节点\n\n"
            "## 代码实现（Python）\n\n"
            "```python\ndef preorder(root):\n"
            "    if not root: return []\n"
            "    return [root.val] + preorder(root.left) + preorder(root.right)\n\n"
            "def inorder(root):\n"
            "    if not root: return []\n"
            "    return inorder(root.left) + [root.val] + inorder(root.right)\n\n"
            "def bfs(root):\n"
            "    if not root: return []\n"
            "    queue, result = [root], []\n"
            "    while queue:\n"
            "        node = queue.pop(0)\n"
            "        result.append(node.val)\n"
            "        if node.left: queue.append(node.left)\n"
            "        if node.right: queue.append(node.right)\n"
            "    return result\n```"
        ),
        "course": "数据结构",
        "tags": ["二叉树", "遍历", "DFS", "BFS"],
    },
    {
        "title": "图的基本概念与存储",
        "content": (
            "图是由顶点（Vertex）和边（Edge）组成的数据结构，用于表示对象之间的关系。\n\n"
            "## 图的分类\n\n"
            "- **有向图 vs 无向图**：边是否有方向\n"
            "- **加权图 vs 无权图**：边是否带有权值\n"
            "- **简单图**：无自环、无重边\n"
            "- **完全图**：任意两个顶点之间都有边\n\n"
            "## 存储方式\n\n"
            "### 邻接矩阵\n用二维数组表示，matrix[i][j] = 1 表示顶点 i 和 j 之间有边。\n"
            "优点：查询快 O(1)。缺点：空间 O(V²)，稀疏图浪费空间。\n\n"
            "### 邻接表\n每个顶点维护一个邻居列表。\n"
            "优点：空间 O(V+E)，适合稀疏图。缺点：查询某条边是否存在需 O(degree)。\n\n"
            "## 实际应用场景\n\n"
            "社交网络（用户关系）、地图导航（道路网络）、课程先修关系（有向无环图）、"
            "网页链接结构、推荐系统等。"
        ),
        "course": "数据结构",
        "tags": ["图", "数据结构", "邻接矩阵", "邻接表"],
    },
    {
        "title": "图的广度优先搜索（BFS）",
        "content": (
            "BFS 从起始顶点开始，逐层向外扩展访问，使用队列实现。\n\n"
            "## 算法步骤\n\n"
            "1. 将起始顶点加入队列，标记为已访问\n"
            "2. 从队列取出一个顶点，访问其所有未访问的邻居\n"
            "3. 将邻居加入队列并标记为已访问\n"
            "4. 重复步骤 2-3，直到队列为空\n\n"
            "## 代码实现\n\n"
            "```python\nfrom collections import deque\n\n"
            "def bfs(graph, start):\n"
            "    visited = set([start])\n"
            "    queue = deque([start])\n"
            "    order = []\n"
            "    while queue:\n"
            "        vertex = queue.popleft()\n"
            "        order.append(vertex)\n"
            "        for neighbor in graph[vertex]:\n"
            "            if neighbor not in visited:\n"
            "                visited.add(neighbor)\n"
            "                queue.append(neighbor)\n"
            "    return order\n```\n\n"
            "## 应用场景\n\n"
            "- **最短路径**：在无权图中，BFS 可找到两点间最短路径\n"
            "- **连通性检测**：判断图中所有顶点是否连通\n"
            "- **拓扑排序**：课程安排、任务调度\n"
            "- **社交网络**：六度分隔理论验证"
        ),
        "course": "算法",
        "tags": ["BFS", "图", "最短路径"],
    },
    {
        "title": "动态规划入门",
        "content": (
            "动态规划（Dynamic Programming, DP）是解决多阶段决策问题的方法论。\n\n"
            "## 核心思想\n\n"
            "将复杂问题分解为重叠子问题，通过求解并记忆子问题的解来避免重复计算。\n\n"
            "## 适用条件\n\n"
            "1. **最优子结构**：问题的最优解包含子问题的最优解\n"
            "2. **重叠子问题**：递归求解时会反复遇到相同的子问题\n\n"
            "## 解题步骤\n\n"
            "1. 定义状态（dp 数组的含义）\n"
            "2. 找出状态转移方程\n"
            "3. 确定初始条件和边界情况\n"
            "4. 确定计算顺序（保证计算当前状态时，所需子状态已计算）\n\n"
            "## 经典例题\n\n"
            "### 斐波那契数列\n"
            "dp[i] = dp[i-1] + dp[i-2]，初始 dp[0]=0, dp[1]=1\n\n"
            "### 0-1 背包问题\n"
            "dp[i][w] = max(dp[i-1][w], dp[i-1][w-weight[i]] + value[i])\n\n"
            "### 最长公共子序列（LCS）\n"
            "若 s1[i]==s2[j]：dp[i][j] = dp[i-1][j-1] + 1\n"
            "否则：dp[i][j] = max(dp[i-1][j], dp[i][j-1])"
        ),
        "course": "算法",
        "tags": ["动态规划", "DP", "算法"],
    },
    {
        "title": "Python 基础语法",
        "content": (
            "Python 是一门简洁易学的编程语言，适合初学者入门。\n\n"
            "## 变量与数据类型\n\n"
            "Python 是动态类型语言，无需声明变量类型：\n"
            "```python\nname = 'Alice'   # 字符串\nage = 25          # 整数\nheight = 1.70     # 浮点数\nis_student = True # 布尔值\n```\n\n"
            "## 控制流\n\n"
            "```python\nif score >= 90:\n    grade = 'A'\nelif score >= 80:\n    grade = 'B'\nelse:\n    grade = 'C'\n\nfor i in range(5):\n    print(i)\n\nwhile count > 0:\n    count -= 1\n```\n\n"
            "## 函数定义\n\n"
            "```python\ndef greet(name, greeting='Hello'):\n    return f'{greeting}, {name}!'\n\n# Lambda 表达式\nsquare = lambda x: x ** 2\n```\n\n"
            "## 常用数据结构\n\n"
            "- **列表（list）**：有序可变序列 `[1, 2, 3]`\n"
            "- **元组（tuple）**：有序不可变序列 `(1, 2, 3)`\n"
            "- **字典（dict）**：键值对集合 `{'name': 'Alice', 'age': 25}`\n"
            "- **集合（set）**：无序不重复元素集 `{1, 2, 3}`"
        ),
        "course": "编程基础",
        "tags": ["Python", "编程", "基础"],
    },
]


async def seed():
    """Seed sample documents if the database is empty."""
    try:
        seekdb_service.init_client()
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        return

    existing = await seekdb_service.list_documents()
    if existing:
        logger.info(f"Database already has {len(existing)} documents, skipping seed")
        return

    logger.info("Seeding sample learning materials...")
    for doc in SAMPLE_DOCUMENTS:
        doc_id = await seekdb_service.insert_document(**doc)
        logger.info(f"  Seeded: {doc['title']} (id={doc_id})")

    logger.info(f"Done. Seeded {len(SAMPLE_DOCUMENTS)} documents.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    asyncio.run(seed())
