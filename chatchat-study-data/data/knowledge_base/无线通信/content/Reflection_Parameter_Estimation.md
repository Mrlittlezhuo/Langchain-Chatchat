# 基于协同消零投影的漫反射参数联合盲反演算法

> 算法参考文档 — 在 AoA 和 TDOA 估计的基础上，从多 UAV 的接收能量中盲提取镜面反射方向 $\mathbf{r}_{spec}$ 和表面粗糙度 $\alpha_R$。
>
> 本文档与 [3D_AoA_Estimation_Algorithm.md](3D_AoA_Estimation_Algorithm.md) 及 [TDOA_Estimation_Algorithm.md](TDOA_Estimation_Algorithm.md) 协同，构成盲几何重建链条中第一层的三维信息提取体系（角度、时延、能量）。
>
> **本文档对原始推导进行了逐步骤数学验证，明确了与现有算法框架的接口。当前模型假设各 UAV 到反射点的路径损耗一致（不包含 $d^{-2}$ 因子），与现有仿真代码保持一致。:warning: 标注了各项前提条件。**

---

## 目录

1. [问题定位](#1-问题定位)
2. [推导验证：从信道模型到能量方程](#2-推导验证从信道模型到能量方程)
   - 2.1 [波束成形与功率提取](#21-波束成形与功率提取)
   - 2.2 [噪声剔除与能量方程](#22-噪声剔除与能量方程)
   - 2.3 [对数线性化](#23-对数线性化)
3. [未知发射功率的消零投影](#3-未知发射功率的消零投影)
4. [VARPRO 参数降维联合估计](#4-varpro-参数降维联合估计)
   - 4.1 [粗糙度的条件闭式解](#41-粗糙度的条件闭式解)
   - 4.2 [镜面反射方向的降维搜索](#42-镜面反射方向的降维搜索)
   - 4.3 [梯度与 Gauss-Newton 海森矩阵](#43-梯度与-gauss-newton-海森矩阵)
5. [与 AoA 算法的接口](#5-与-aoa-算法的接口)
6. [在盲几何重建中的角色](#6-在盲几何重建中的角色)
7. [数值考虑与实现要点](#7-数值考虑与实现要点)

---

## 1. 问题定位

### 1.1 动机

在盲几何重建的前两步中已获取：

| 来源 | 输出 | 约束 |
|------|------|------|
| SA2N / Grid2N | $\hat{\bm{\Omega}}_{n,k}$ | 来波方向 |
| 互功率谱 WLS | $\Delta\hat{\tau}_{n,k,1}$, $\Delta\hat{d}_{n,k,1}$ | 距离差 |

**本算法从第三维度——接收能量——提取反射面的几何参数（镜面反射方向 $\mathbf{r}_{spec}$）和物理参数（粗糙度 $\alpha_R$）。**

### 1.2 核心思想

同一波束 $n$ 被反射面散射后到达 $K$ 个 UAV。因 Phong 漫反射波瓣的方向性，不同 UAV 接收能量取决于其偏离镜面方向 $\mathbf{r}_{spec}$ 的角度 $\beta$。比较 $K$ 个 UAV 的能量差异 → 反演 $\mathbf{r}_{spec}$ 和 $\alpha_R$。**全程 BS 发射功率未知。**

### 1.3 在盲重建链条中的位置

```
第一层 [信号 → 角度 + 时延 + 能量]
  ├── 1a. AoA  ← SA2N / Grid2N
  ├── 1b. TDOA ← 互功率谱 WLS
  └── 1c. 反射参数 ← 本文档
       输入: 波束成形标量信号 + AoA + σ_n²
       输出: r̂_{spec,n} (镜面方向) + α̂_R (粗糙度)

第二层 [→ 反射点 + UAV 位置]
  联合 AoA + DDOA + 镜面方向

第三层 [→ 反射面 → BS]
  r_{spec} = v̂_in - 2(v̂_in^T n)n  → 约束法向量 → BS
```

---

## 2. 推导验证：从信道模型到能量方程

### 2.1 波束成形与功率提取

从 AoA 估计得到 $\hat{\bm{\Omega}}_{n,k}$ 后，波束成形提取标量信号（与 TDOA 算法统一的末归一化形式）：

$$
y_{n,k,i,m} = \left[\mathbf{a}_{\rm{rx}}^{(i)}(\hat{\bm{\Omega}}_{n,k})\right]^H \mathbf{r}_{n,k,i,m}
$$

展开得：

$$
y_{n,k,i,m} = \tilde{\alpha}_{n,k} \cdot e^{-j 2\pi f_i \tau_{n,k}} \cdot s_{n,i,m} + \tilde{n}_{n,k,i,m}
$$

其中 $\tilde{\alpha}_{n,k} = N_t N_r \cdot \left(\frac{1+\cos\beta_{n,k}}{2}\right)^{\frac{\alpha_R}{2}}$，$\tilde{n}$ 方差为 $N_r \sigma_n^2$。

**跨子载波和快拍的功率平均**：

$$
\hat{P}_{\text{total}, n,k} = \frac{1}{I M} \sum_{i=0}^{I-1} \sum_{m=1}^{M} |y_{n,k,i,m}|^2
$$

展开 $|y|^2$ 后，$s$ 与 $\tilde{n}$ 的交叉项均值为零。利用 $\mathbb{E}[|s|^2] = \sigma_s^2$ 和 $\mathbb{E}[|\tilde{n}|^2] = N_r \sigma_n^2$：

$$
\hat{P}_{\text{total}, n,k} \approx |\tilde{\alpha}_{n,k}|^2 \sigma_s^2 + N_r \sigma_n^2
$$

### 2.2 噪声剔除与能量方程

噪声功率 $\sigma_n^2$ 来自 ML 框架闭式解（见 AoA 文档 §5.2）：

$$
\sigma_n^2 = \frac{\operatorname{tr}(\mathbf{R}_{\mathbf{n,k}}^{(i)}) - J^{(i)}(\hat{\bm{\Omega}}_{n,k})}{N_r - 1}
$$

剔除噪声：

$$
\boxed{\tilde{P}_{n,k} = \hat{P}_{\text{total}, n,k} - N_r \sigma_n^2 = |\tilde{\alpha}_{n,k}|^2 \sigma_s^2}
$$

代入 $|\tilde{\alpha}_{n,k}|^2 = (N_t N_r)^2 \cdot \left(\frac{1+\cos\beta_{n,k}}{2}\right)^{\alpha_R}$（注意：能域指数为 $\alpha_R$，论文振幅域为 $\alpha_R/2$）：

$$
\boxed{\tilde{P}_{n,k} = \underbrace{(N_t N_r)^2 \sigma_s^2}_{C_0} \cdot \left(\frac{1+\cos\beta_{n,k}}{2}\right)^{\alpha_R}}
$$

$C_0$ 包含 BS 阵元数、UAV 阵元数、发射功率——全部未知，但对于同一波束所有 UAV 相同。

### 2.3 对数线性化

从 AoA 获取出射方向：

$$
\mathbf{v}_{\text{out},k} = \begin{bmatrix} \sin\hat{\theta}_{r,n,k} \cos\hat{\varphi}_{r,n,k} \\ \sin\hat{\theta}_{r,n,k} \sin\hat{\varphi}_{r,n,k} \\ \cos\hat{\theta}_{r,n,k} \end{bmatrix}
$$

> 注：AoA 估计的 $(\hat{\varphi}, \hat{\theta})$ 对应波传播方向（反射点 → UAV），即 $\mathbf{v}_{\text{out},k}$ 本身，无需取反。

则 $\cos\beta_{n,k} = \mathbf{r}_{spec}^T \mathbf{v}_{\text{out},k}$（两者均为单位向量）。

取对数：

$$
\ln\tilde{P}_{n,k} = \underbrace{\ln C_0}_{c} + \alpha_R \cdot \underbrace{\ln\left(\frac{1 + \mathbf{r}_{spec}^T \mathbf{v}_{\text{out},k}}{2}\right)}_{g_k(\mathbf{r}_{spec})}
$$

其中函数 $g_k: \mathbb{S}^2 \to \mathbb{R}$ 定义为：

$$
\boxed{g_k(\mathbf{r}) \triangleq \ln\left(\frac{1 + \mathbf{r}^T \mathbf{v}_{\text{out},k}}{2}\right)}, \qquad \forall \mathbf{r} \in \mathbb{S}^2
$$

上式即 $g_k$ 在真值 $\mathbf{r}_{spec}$ 处的取值。定义 $z_k = \ln\tilde{P}_{n,k}$，$c = \ln C_0$。将 $K$ 个 UAV 的方程堆叠，记 $\mathbf{g}(\mathbf{r}) = [g_1(\mathbf{r}), \ldots, g_K(\mathbf{r})]^T$：

$$
\boxed{\mathbf{z} = c \mathbf{1}_{K \times 1} + \alpha_R \, \mathbf{g}(\mathbf{r}_{spec})}
$$

---

## 3. 未知发射功率的消零投影

### 3.1 零空间投影矩阵

$c = \ln C_0$ 未知导致绝对能量尺度模糊。利用 $c$ 乘以全 1 向量的结构，通过零空间投影消除：

$$
\boxed{\mathbf{P}^\perp = \mathbf{I}_K - \frac{1}{K} \mathbf{1}_{K \times 1} \mathbf{1}_{K \times 1}^T \quad \in \mathbb{R}^{K \times K}}
$$

**验证**：$\mathbf{P}^\perp \mathbf{1} = \mathbf{1} - \frac{1}{K} \cdot K \cdot \mathbf{1} = \mathbf{0}$ ✓

几何解释：$\mathbf{P}^\perp$ 将 $K$ 维向量投影到与全 1 向量正交的 $(K-1)$ 维子空间。

### 3.2 投影后的净化方程

$$
\begin{aligned}
\mathbf{P}^\perp \mathbf{z} &= c \underbrace{\mathbf{P}^\perp \mathbf{1}}_{=\mathbf{0}} + \alpha_R \, \mathbf{P}^\perp \mathbf{g}(\mathbf{r}_{spec}) = \alpha_R \, \mathbf{P}^\perp \mathbf{g}(\mathbf{r}_{spec})
\end{aligned}
$$

定义投影后变量：

$$
\boxed{\tilde{\mathbf{z}} \triangleq \mathbf{P}^\perp \mathbf{z}, \qquad \tilde{\mathbf{g}}(\mathbf{r}) \triangleq \mathbf{P}^\perp \mathbf{g}(\mathbf{r})}
$$

得到**净化方程**（不再含未知常数 $c$）：

$$
\boxed{\tilde{\mathbf{z}} = \alpha_R \cdot \tilde{\mathbf{g}}(\mathbf{r}_{spec})}
$$

> :warning: **前提 ②**：投影后向量存在于 $(K-1)$ 维子空间。至少需要 $K \ge 3$ 个 UAV（$K \ge 4$ 推荐）。

---

## 4. VARPRO 参数降维联合估计

净化方程构成可分离非线性最小二乘 (SNLLS)：$\alpha_R$ 为线性参数（条件闭式解），$\mathbf{r}_{spec}$ 为非线性参数（单位球面 $\mathbb{S}^2$ 上 2D 搜索）。

### 4.1 粗糙度的条件闭式解

对给定 $\mathbf{r}$，$\tilde{\mathbf{z}} = \alpha_R \tilde{\mathbf{g}}(\mathbf{r})$ 的最小二乘解：

$$
\boxed{\hat{\alpha}_R(\mathbf{r}) = \left(\tilde{\mathbf{g}}^T \tilde{\mathbf{g}}\right)^{-1} \tilde{\mathbf{g}}^T \tilde{\mathbf{z}} = \frac{\tilde{\mathbf{g}}^T(\mathbf{r}) \tilde{\mathbf{z}}}{\|\tilde{\mathbf{g}}(\mathbf{r})\|^2}}
$$

向量内积比，$O(K)$ 计算。

### 4.2 镜面反射方向的降维搜索

将 $\hat{\alpha}_R(\mathbf{r})$ 代回，构造仅依赖 $\mathbf{r}$ 的降维代价函数：

$$
\boxed{J(\mathbf{r}) = \left\| \tilde{\mathbf{z}} - \frac{\tilde{\mathbf{g}}^T(\mathbf{r}) \tilde{\mathbf{z}}}{\|\tilde{\mathbf{g}}(\mathbf{r})\|^2} \, \tilde{\mathbf{g}}(\mathbf{r}) \right\|^2}
$$

$J(\mathbf{r})$ 为 $\tilde{\mathbf{z}}$ 到 $\tilde{\mathbf{g}}(\mathbf{r})$ 张成的 1D 子空间的正交距离平方。

**参数化**：$\mathbf{r}_{spec}$ 为 $\mathbb{S}^2$ 单位向量，2 自由度：

$$
\mathbf{r}_{spec}(\varphi, \theta) = \begin{bmatrix} \sin\theta \cos\varphi \\ \sin\theta \sin\varphi \\ \cos\theta \end{bmatrix}, \quad \varphi \in [-\pi, \pi],\; \theta \in [0, \pi]
$$

| 搜索策略 | 步长 | 点数 |
|----------|------|------|
| 粗搜索 | $5^\circ$ | $72 \times 36 = 2592$ |
| 精炼 (Gauss-Newton) | — | $< 20$ 迭代 |

**最终估计**：

$$
\boxed{\begin{aligned}
\hat{\mathbf{r}}_{spec,n} &= \arg\min_{\|\mathbf{r}\|=1} J(\mathbf{r}) \\[6pt]
\hat{\alpha}_R &= \frac{\tilde{\mathbf{g}}^T(\hat{\mathbf{r}}_{spec,n}) \, \tilde{\mathbf{z}}}{\|\tilde{\mathbf{g}}(\hat{\mathbf{r}}_{spec,n})\|^2}
\end{aligned}}
$$

每个波束 $n$ 产生独立 $\hat{\mathbf{r}}_{spec,n}$，粗糙度 $\hat{\alpha}_R$ 应对所有波束一致（反射面固有属性）。

### 4.3 梯度与 Gauss-Newton 海森矩阵

**预备定义**。本节涉及以下变量（部分复用前文定义）：

| 符号 | 维度 | 含义 | 来源 |
|------|------|------|------|
| $\boldsymbol{\eta} = [\varphi, \theta]^T$ | $2 \times 1$ | 镜面反射方向的球面参数（搜索变量） | 本文 |
| $\mathbf{r}(\boldsymbol{\eta})$ | $3 \times 1$ | 单位球面嵌入映射 | §4.2 式 |
| $\mathbf{v}_{\text{out},k}$ | $3 \times 1$ | 反射点→第 $k$ 个 UAV 的单位出射方向 | §2.3 式 |
| $\tilde{\mathbf{z}}$ | $K \times 1$ | 投影后对数功率观测 | §3.2 式 |
| $\tilde{\mathbf{g}}(\mathbf{r})$ | $K \times 1$ | 投影后对数 Phong 映射 | §3.2 式 |
| $\alpha(\mathbf{r}) = \frac{\tilde{\mathbf{g}}^T\tilde{\mathbf{z}}}{\|\tilde{\mathbf{g}}\|^2}$ | 标量 | 粗糙度的条件闭式解 | §4.1 式 |
| $\mathbf{e}(\mathbf{r}) = \tilde{\mathbf{z}} - \alpha\tilde{\mathbf{g}}$ | $K \times 1$ | 残差向量 | 本文 |
| $w_k(\mathbf{r}) = \frac{1}{1 + \mathbf{r}^T\mathbf{v}_{\text{out},k}}$ | 标量 | 第 $k$ 个 UAV 的 Phong 权重倒数（$\mathbf{r}$ 为搜索方向 $\mathbf{r}(\boldsymbol{\eta})$） | 本文 |
| $\mathbf{P}^\perp = \mathbf{I}_K - \frac{1}{K}\mathbf{1}\mathbf{1}^T$ | $K \times K$ | 零空间投影矩阵 | §3.1 式 |
| $K$ | 标量 | UAV 数量 | §1 |

注意：代价函数 $J$ 的变量转换——前文定义 $J(\mathbf{r})$ 以 3D 方向向量为自变量（§4.2 式），本节省略参数化链条，记 $J(\boldsymbol{\eta}) \triangleq J(\mathbf{r}(\boldsymbol{\eta}))$，$\tilde{\mathbf{g}}(\boldsymbol{\eta}) \triangleq \tilde{\mathbf{g}}(\mathbf{r}(\boldsymbol{\eta}))$，依此类推。

**VARPRO 梯度简化**。利用 $\alpha$ 的最小二乘最优性，残差与回归量正交：

$$
\mathbf{e}^T \tilde{\mathbf{g}} = (\tilde{\mathbf{z}} - \alpha\tilde{\mathbf{g}})^T\tilde{\mathbf{g}} = \tilde{\mathbf{z}}^T\tilde{\mathbf{g}} - \frac{\tilde{\mathbf{g}}^T\tilde{\mathbf{z}}}{\|\tilde{\mathbf{g}}\|^2}\|\tilde{\mathbf{g}}\|^2 = 0
$$

$J(\boldsymbol{\eta}) = \|\mathbf{e}(\boldsymbol{\eta})\|^2$ 对第 $j$ 个参数 $\eta_j$（$j=1$ 时 $\eta_1 = \varphi$，$j=2$ 时 $\eta_2 = \theta$）的偏导数。由链式法则：

$$
\frac{\partial\mathbf{e}}{\partial\eta_j} = -\frac{\partial(\alpha\tilde{\mathbf{g}})}{\partial\eta_j} = -\alpha\frac{\partial\tilde{\mathbf{g}}}{\partial\eta_j} - \tilde{\mathbf{g}}\frac{\partial\alpha}{\partial\eta_j}
$$

于是：

$$
\frac{\partial J}{\partial \eta_j} = 2\mathbf{e}^T \frac{\partial\mathbf{e}}{\partial\eta_j} = -2\mathbf{e}^T \left( \tilde{\mathbf{g}} \frac{\partial\alpha}{\partial\eta_j} + \alpha \frac{\partial\tilde{\mathbf{g}}}{\partial\eta_j} \right) = -2\alpha \mathbf{e}^T \frac{\partial\tilde{\mathbf{g}}}{\partial\eta_j}
$$

其中 $\tilde{\mathbf{g}} \frac{\partial\alpha}{\partial\eta_j}$ 项因 $\mathbf{e}^T\tilde{\mathbf{g}} = 0$ 消失——这是 VARPRO 降维的核心优势：线性参数 $\alpha$ 的导数不出现在梯度中。

定义 $\tilde{\mathbf{g}}$ 对 $\boldsymbol{\eta}$ 的雅可比矩阵 $\mathbf{J}_g \in \mathbb{R}^{K \times 2}$，其第 $(k,j)$ 元素为 $[\mathbf{J}_g]_{k,j} = \frac{\partial \tilde{g}_k}{\partial \eta_j}$。梯度写成矩阵形式：

$$
\boxed{\nabla_{\boldsymbol{\eta}} J = -2\alpha \, \mathbf{J}_g^T \mathbf{e} \quad \in \mathbb{R}^{2 \times 1}}
$$

**球面参数化**。$\mathbf{r}_{spec}$ 为单位向量，参数化为 $\mathbf{r}(\varphi,\theta)$，其一阶和二阶切向量为：

$$
\mathbf{r}(\varphi,\theta) = \begin{bmatrix} \sin\theta \cos\varphi \\ \sin\theta \sin\varphi \\ \cos\theta \end{bmatrix}, \quad
\mathbf{r}_\varphi = \frac{\partial\mathbf{r}}{\partial\varphi} = \begin{bmatrix} -\sin\theta \sin\varphi \\ \sin\theta \cos\varphi \\ 0 \end{bmatrix}, \quad
\mathbf{r}_\theta = \frac{\partial\mathbf{r}}{\partial\theta} = \begin{bmatrix} \cos\theta \cos\varphi \\ \cos\theta \sin\varphi \\ -\sin\theta \end{bmatrix}
$$

（二阶切向量 $\mathbf{r}_{\varphi\varphi}, \mathbf{r}_{\theta\theta}, \mathbf{r}_{\varphi\theta}$ 见附录，GN 近似中不使用。）

**雅可比矩阵 $\mathbf{J}_g$ 的构造**。目标是求 $\tilde{\mathbf{g}}$ 对 $\boldsymbol{\eta}$ 的雅可比。分三步：

**(1) 写出 $\tilde{g}_k$ 的分量形式。** 由 §3.2：$\tilde{\mathbf{g}} = \mathbf{P}^\perp \mathbf{g}$，写成分量：

$$
\tilde{g}_k = \sum_{\ell=1}^K P^\perp_{k\ell} \, g_\ell, \qquad k = 1, \ldots, K
$$

其中 $g_\ell$ 即 §2.3 定义的函数 $g_\ell(\mathbf{r}) = \ln\frac{1 + \mathbf{r}^T\mathbf{v}_{\text{out},\ell}}{2}$（此处 $\mathbf{r}$ 为搜索变量），$P^\perp_{k\ell}$ 是 $\mathbf{P}^\perp$ 的 $(k,\ell)$ 元素，为常数。

**(2) 对 $\eta_j$ 求偏导。** $\mathbf{P}^\perp$ 不依赖 $\boldsymbol{\eta}$，由求导的线性性：

$$
\frac{\partial \tilde{g}_k}{\partial \eta_j} = \frac{\partial}{\partial \eta_j} \sum_{\ell=1}^K P^\perp_{k\ell} \, g_\ell = \sum_{\ell=1}^K P^\perp_{k\ell} \frac{\partial g_\ell}{\partial \eta_j}
$$

这正是 $\mathbf{J}_g$ 的第 $(k,j)$ 元素：

$$
\boxed{[\mathbf{J}_g]_{k,j} = \frac{\partial \tilde{g}_k}{\partial \eta_j} = \sum_{\ell=1}^K P^\perp_{k\ell} \frac{\partial g_\ell}{\partial \eta_j}}, \qquad \mathbf{J}_g \in \mathbb{R}^{K \times 2}
$$

**(3) 计算 $\frac{\partial g_\ell}{\partial \eta_j}$。** 对 $g_\ell(\mathbf{r}) = \ln\frac{1 + \mathbf{r}^T\mathbf{v}_{\text{out},\ell}}{2}$ 求导（$g_\ell$ 与 $g_k$ 为同一函数，下标 $\ell$ 对应求和遍历的 UAV）：

$$
\frac{\partial g_\ell}{\partial \varphi} = \frac{1}{1 + \mathbf{r}^T\mathbf{v}_{\text{out},\ell}} \cdot \mathbf{v}_{\text{out},\ell}^T \mathbf{r}_\varphi = w_\ell \cdot \mathbf{v}_{\text{out},\ell}^T \mathbf{r}_\varphi
$$

$$
\frac{\partial g_\ell}{\partial \theta} = w_\ell \cdot \mathbf{v}_{\text{out},\ell}^T \mathbf{r}_\theta
$$

其中 $w_\ell \triangleq \frac{1}{1 + \mathbf{r}^T\mathbf{v}_{\text{out},\ell}}$，$\mathbf{r}_\varphi, \mathbf{r}_\theta$ 如上文球面参数化所定义。

**梯度显式分量**。注意到 $\mathbf{e}$ 已处于投影子空间：$\mathbf{P}^\perp\mathbf{e} = \mathbf{P}^\perp(\tilde{\mathbf{z}} - \alpha\tilde{\mathbf{g}}) = \tilde{\mathbf{z}} - \alpha\tilde{\mathbf{g}} = \mathbf{e}$（因 $\tilde{\mathbf{z}} = \mathbf{P}^\perp\mathbf{z}$ 和 $\tilde{\mathbf{g}} = \mathbf{P}^\perp\mathbf{g}$ 已在投影子空间内）。由此 $\mathbf{P}^\perp$ 在梯度中可消去：

$$
\frac{\partial J}{\partial \eta_j} = -2\alpha \mathbf{e}^T \frac{\partial\tilde{\mathbf{g}}}{\partial\eta_j} = -2\alpha \mathbf{e}^T \mathbf{P}^\perp \frac{\partial\mathbf{g}}{\partial\eta_j} = -2\alpha (\mathbf{P}^\perp\mathbf{e})^T \frac{\partial\mathbf{g}}{\partial\eta_j} = -2\alpha \mathbf{e}^T \frac{\partial\mathbf{g}}{\partial\eta_j}
$$

即梯度计算中可直接使用原始（未投影）的 $\frac{\partial g_k}{\partial\eta_j}$ 求和，无需显式构建 $\mathbf{P}^\perp$。

将 $\frac{\partial g_k}{\partial\varphi} = w_k \mathbf{v}_{\text{out},k}^T\mathbf{r}_\varphi$ 和 $\frac{\partial g_k}{\partial\theta} = w_k \mathbf{v}_{\text{out},k}^T\mathbf{r}_\theta$ 代入。令 $e_k$ 为残差向量 $\mathbf{e}$ 的第 $k$ 个分量，展开内积：

$$
\boxed{\frac{\partial J}{\partial \varphi} = -2\alpha \sum_{k=1}^K e_k \frac{\mathbf{v}_{\text{out},k}^T \mathbf{r}_\varphi}{1 + \mathbf{r}^T\mathbf{v}_{\text{out},k}}, \qquad
\frac{\partial J}{\partial \theta} = -2\alpha \sum_{k=1}^K e_k \frac{\mathbf{v}_{\text{out},k}^T \mathbf{r}_\theta}{1 + \mathbf{r}^T\mathbf{v}_{\text{out},k}}}
$$

其中 $\mathbf{r}$ 为当前搜索方向 $\mathbf{r}(\boldsymbol{\eta})$。计算复杂度 $O(K)$，每次梯度求值仅需 $K$ 次内积。

**牛顿法需要海森矩阵**。梯度下降只用一阶信息，收敛慢。牛顿法利用二阶信息（海森矩阵 $\nabla^2 J$）构造更新方向 $\mathbf{d} = -(\nabla^2 J)^{-1} \nabla J$，具有局部二次收敛速度。$J = \|\mathbf{e}\|^2 = \sum_{k=1}^K e_k^2$，逐元素求导得真实海森：

$$
\nabla^2 J = 2 \underbrace{\left(\frac{\partial\mathbf{e}}{\partial\boldsymbol{\eta}}\right)^T \left(\frac{\partial\mathbf{e}}{\partial\boldsymbol{\eta}}\right)}_{\text{一阶项：仅含 } \partial e_k/\partial\eta_j} \;+\; 2\sum_{k=1}^K e_k \underbrace{\frac{\partial^2 e_k}{\partial\boldsymbol{\eta}^2}}_{\text{二阶项：含 } \partial^2 e_k/\partial\eta_i\partial\eta_j}
$$

**为什么二阶项可以扔掉**。关键在于每一项都是 **$e_k \times \frac{\partial^2 e_k}{\partial\boldsymbol{\eta}^2}$**。当搜索方向 $\mathbf{r}$ 接近真实的镜面方向 $\mathbf{r}_{spec}$ 时，每条功率方程 $z_k \approx c + \alpha_R g_k(\mathbf{r})$ 的拟合误差很小，即 $e_k \to 0$。无论 $\frac{\partial^2 e_k}{\partial\boldsymbol{\eta}^2}$ 本身多大，乘积 $e_k \cdot \frac{\partial^2 e_k}{\partial\boldsymbol{\eta}^2}$ 都趋于零。

反之，一阶项中的 $\frac{\partial e_k}{\partial\eta_j}$ 取决于 $\mathbf{v}_{\text{out},k}$ 和 $\mathbf{P}^\perp$（纯几何量，不随拟合精度变化），在最优解处也不为零——它是海森的主导项。

打个比方：把 $J$ 在最优解附近做 Taylor 展开，一阶项是「斜坡的坡度」（永远存在），二阶项是「斜坡的弯曲度」乘以「离最低点还有多远」——越靠近最低点，弯曲度的贡献越小。

**对我们的问题意味着什么**。$\mathbf{e} = \tilde{\mathbf{z}} - \alpha\tilde{\mathbf{g}}$ 的二阶导涉及 $\frac{\partial\alpha}{\partial\boldsymbol{\eta}}$ 和 $\frac{\partial^2\tilde{g}_k}{\partial\boldsymbol{\eta}^2}$，推导繁琐。但因为粗搜索已经把 $(\varphi, \theta)$ 送到最优解附近（$5^\circ$ 精度），残差 $\|\mathbf{e}\|$ 已经不大，扔掉二阶项是安全的。

**Gauss-Newton 近似**。扔掉 $\sum_k e_k \nabla^2 e_k$ 后，海森简化为仅含一阶导的形式。此时残差雅可比可进一步近似为 $\frac{\partial\mathbf{e}}{\partial\boldsymbol{\eta}} \approx -\alpha\frac{\partial\tilde{\mathbf{g}}}{\partial\boldsymbol{\eta}} = -\alpha\mathbf{J}_g$（因为 $\mathbf{e} = \tilde{\mathbf{z}} - \alpha\tilde{\mathbf{g}}$，而 $\tilde{\mathbf{z}}$ 不依赖 $\boldsymbol{\eta}$，$\alpha$ 对 $\boldsymbol{\eta}$ 的变化也被归入被扔掉的二阶项）：

$$
\boxed{\mathbf{H}_{GN} = 2(-\alpha\mathbf{J}_g)^T(-\alpha\mathbf{J}_g) = 2\alpha^2 \, \mathbf{J}_g^T \mathbf{J}_g \quad \in \mathbb{R}^{2 \times 2}}
$$

**显式计算**。$\mathbf{H}_{GN}$ 是 $2 \times 2$ 矩阵，直接展开：

$$
\mathbf{H}_{GN} = 2\alpha^2 \begin{bmatrix}
\displaystyle\sum_{k=1}^K \left(\frac{\partial\tilde{g}_k}{\partial\varphi}\right)^2 & \displaystyle\sum_{k=1}^K \frac{\partial\tilde{g}_k}{\partial\varphi}\frac{\partial\tilde{g}_k}{\partial\theta} \\[12pt]
\displaystyle\sum_{k=1}^K \frac{\partial\tilde{g}_k}{\partial\theta}\frac{\partial\tilde{g}_k}{\partial\varphi} & \displaystyle\sum_{k=1}^K \left(\frac{\partial\tilde{g}_k}{\partial\theta}\right)^2
\end{bmatrix}
$$

其中 $\frac{\partial\tilde{g}_k}{\partial\varphi} = \sum_{\ell=1}^K P^\perp_{k\ell} \, w_\ell \, \mathbf{v}_{\text{out},\ell}^T \mathbf{r}_\varphi$（同理 $\partial\theta$），已在 Jacobian 构造中给出。注意这里的 $\mathbf{P}^\perp$ **不能像梯度那样消去**——海森依赖的是 $\tilde{\mathbf{g}}$ 的导数，不是 $\mathbf{g}$ 的导数。

**牛顿迭代**。有了梯度和 GN 海森，迭代更新为：

$$
\boldsymbol{\eta}^{(t+1)} = \boldsymbol{\eta}^{(t)} - \mathbf{H}_{GN}^{-1} \nabla_{\boldsymbol{\eta}} J
$$

每次迭代后施加角度约束：$\varphi \leftarrow \text{wrapToPi}(\varphi)$，$\theta \leftarrow \max(0, \min(\pi, \theta))$。收敛判据：$\|\Delta\boldsymbol{\eta}\| < 10^{-5}$ 或达到 20 次迭代上限。

**实用细节**。

(1) *正则化*：当 UAV 几何构型退化时 $\mathbf{J}_g$ 可能秩亏，对 $\mathbf{H}_{GN}$ 加 Tikhonov 项：$\mathbf{H}_{GN} \leftarrow \mathbf{H}_{GN} + 10^{-8} \, \mathbf{I}_2$。

(2) *线搜索*：若全步长使代价上升，回退步长 $\gamma \in \{1, \frac{1}{2}, \frac{1}{4}, \ldots, \frac{1}{128}\}$，取首个使 $J$ 下降的 $\gamma$：

$$
\boldsymbol{\eta}^{(t+1)} = \boldsymbol{\eta}^{(t)} - \gamma \, \mathbf{H}_{GN}^{-1} \nabla_{\boldsymbol{\eta}} J
$$

---


## 5. 与 AoA 算法的接口

### 端到端处理流程（单波束 $n$）

```
前置: AoA 估计 (SA2N / Grid2N) → Ω̂_{n,k}, σ_n²

1. 空间滤波 + 功率提取
   y = a_rx^H(Ω̂, λ) · r
   P̂_total = (1/IM) ΣᵢΣₘ |y|²
   P̃ = P̂_total − N_r σ_n²

2. 出射方向
   v_out,k = [sin θ̂ cos φ̂, sin θ̂ sin φ̂, cos θ̂]^T

3. 对数线性化 + 零空间投影
   z_k = ln P̃_k
   g_k(r) = ln((1 + r^T v_out,k) / 2)
   P^⊥ = I_K − (1/K) 1 1^T
   z̃ = P^⊥ z,  g̃(r) = P^⊥ g(r)

4. VARPRO 搜索 (φ, θ) on 𝕊²
   J(r(φ,θ)) = ‖z̃ − (g̃^T z̃ / ‖g̃‖²) g̃‖²
   r̂_spec = arg min J
   α̂_R = g̃^T(r̂_spec) z̃ / ‖g̃(r̂_spec)‖²
```

### 输入输出契约

| 方向 | 内容 | 来源/去向 |
|------|------|-----------|
| **输入** | 协方差张量 $\mathcal{R}_{\mathbf{n,k}}$ | 原始接收信号 |
| **输入** | AoA 估计 $\hat{\bm{\Omega}}_{n,k}$ | SA2N / Grid2N |
| **输入** | 噪声功率 $\sigma_n^2$ | ML 闭式解 |
| **输出** | 镜面方向 $\hat{\mathbf{r}}_{spec,n}$ | → 法向量 $\mathbf{n}$ 求解 |
| **输出** | 粗糙度 $\hat{\alpha}_R$ | → 反射面物理特征 |

---

## 6. 在盲几何重建中的角色

### 镜面反射定律约束

$$
\boxed{\mathbf{r}_{spec,n} = \hat{\mathbf{v}}_{\text{in},n} - 2\left(\hat{\mathbf{v}}_{\text{in},n}^T \mathbf{n}\right) \mathbf{n}}
$$

- $K$ 个 UAV 全部看到**同一** $\mathbf{r}_{spec,n}$
- $N$ 个波束 → $N$ 个 $\mathbf{r}_{spec,n}$，全部受**同一** $\mathbf{n}$ 约束

### 约束汇总

| 约束类型 | 数量 | 来源 |
|----------|------|------|
| AoA 方向 | $NK$ | SA2N / Grid2N |
| DDOA 距离差 | $N(K-1)$ | 互功率谱 WLS |
| 镜面方向 | $N$ | **本文档** |
| 粗糙度 | $1$ | **本文档** |

三个维度独立提供空间约束，大大增强第二层联合求解的可观测性。

---

## 7. 数值考虑与实现要点

### 7.1 对数域定义域

$g_k(\mathbf{r}) = \ln\left(\frac{1 + \mathbf{r}^T \mathbf{v}_{\text{out},k}}{2}\right)$ 要求 $\mathbf{r}^T \mathbf{v}_{\text{out},k} > -1$（即 $\beta \neq \pi$）。当 $\mathbf{r}^T \mathbf{v}_{\text{out},k} < -0.99$ 时，剔除该 UAV 或正则化截断。

### 7.2 噪声功率估计稳健性

$\sigma_n^2$ 的 ML 估计依赖 AoA 准确性。对 $I$ 个子载波分别估计后取中位数以提高稳健性。

### 7.3 多波束 $\alpha_R$ 一致性

$N$ 个波束的独立 $\hat{\alpha}_R^{(n)}$ 应对不同 $n$ 一致。显著偏离者可能遭遇深度衰落或强干扰——可用作离群值检测。

### 7.4 搜索精度

能量对 $\beta$ 的敏感度在镜面方向附近 ($\beta \approx 0$) 最大。粗搜索 $5^\circ$ 步长，精炼至 $0.5^\circ$。

---

## 附录：符号对应

| 本文档 | 论文 | 含义 |
|--------|------|------|
| $\mathbf{r}_{spec,n}$ | $\mathbf{r}_{n,\text{spec}}$ | 镜面反射方向（单位向量） |
| $\mathbf{v}_{\text{out},k}$ | $\mathbf{v}_{n,k,\text{out}} / d_{\text{out}}$ | 反射点指向 UAV $k$ 的单位出射向量 |
| $\beta_{n,k}$ | 同 | 出射方向偏离镜面方向的角度 |
| $\alpha_R$ | 同 | 表面粗糙度（能域指数） |
| $\tilde{P}_{n,k}$ | — | 噪声剔除后的纯净接收能量 |
| $C_0$ | — | 未知系统常数 ($N_t^2 N_r^2 \sigma_s^2$) |
| $c = \ln C_0$ | — | 对数域截距 |
| $\mathbf{P}^\perp$ | — | 消零正交投影矩阵 |
| $\tilde{\mathbf{z}}, \tilde{\mathbf{g}}$ | — | 投影后观测与映射向量 |
| $J(\mathbf{r})$ | — | VARPRO 降维代价函数 |

---

*本文档基于原始推导进行了完整数学验证，修正了归一化约定、扩展了多快拍/多子载波平均，并与现有 AoA 算法文档建立了清晰的接口契约。当前模型假设路径损耗一致（不含 $d^{-2}$ 因子），与仿真代码保持一致。*
