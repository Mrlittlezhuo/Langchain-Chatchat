# 毫米波漫反射信道下基于混合优化的 3D AoA 估计

> 算法参考文档 — 整合论文 "Robust Positioning for mmWave Beam-Scanning in Diffuse Channels via Hybrid Optimization" 的公式推导与 MATLAB 实现。
>
> 本文档中的符号体系以论文为准。对论文中存在的笔误或歧义，以 :warning: 标注并给出修正。

---

## 目录

1. [研究场景与问题定位](#1-研究场景与问题定位)
2. [符号表](#2-符号表)
3. [系统模型](#3-系统模型)
   - 3.1 [空间几何](#31-空间几何)
   - 3.2 [阵列拓扑](#32-阵列拓扑)
   - 3.3 [漫反射衰减模型](#33-漫反射衰减模型)
4. [信号模型](#4-信号模型)
   - 4.1 [OFDM 子载波结构](#41-ofdm-子载波结构)
   - 4.2 [导向矢量](#42-导向矢量)
   - 4.3 [信道矩阵](#43-信道矩阵)
   - 4.4 [接收信号与协方差矩阵](#44-接收信号与协方差矩阵)
5. [最大似然 AoA 估计框架](#5-最大似然-aoa-估计框架)
   - 5.1 [似然函数推导](#51-似然函数推导)
   - 5.2 [未知参数闭式解](#52-未知参数闭式解)
   - 5.3 [目标函数与优化问题](#53-目标函数与优化问题)
   - 5.4 [多子载波扩展](#54-多子载波扩展)
6. [SA2N 算法](#6-sa2n-算法)
   - 6.1 [阶段一：模拟退火](#61-阶段一模拟退火)
   - 6.2 [阶段二：牛顿-拉夫逊迭代](#62-阶段二牛顿-拉夫逊迭代)
7. [Grid2N 算法](#7-grid2n-算法)
   - 7.1 [阶段一：均匀网格采样](#71-阶段一均匀网格采样)
   - 7.2 [阶段二：Top-N 峰值提取](#72-阶段二top-n-峰值提取)
   - 7.3 [阶段三：多起始点牛顿精炼](#73-阶段三多起始点牛顿精炼)
8. [梯度与海森矩阵](#8-梯度与海森矩阵)
9. [坐标系转换：LCS → GCS](#9-坐标系转换lcs--gcs)
10. [算法在盲几何重建中的角色](#10-算法在盲几何重建中的角色)
11. [论文问题与修正](#11-论文问题与修正)

---

## 1. 研究场景与问题定位

### 1.1 总体问题：盲几何重建

考虑如下场景：

```
       BS (位置 ???)
        |
        | N 个等角间隔波束 (方向 ???)
        v
  ═══════════════════════  粗糙反射面 (位置/朝向/法向量 均 ???)
       /|\
      / | \  漫反射
     /  |  \
    v   v   v
  UAV₁ UAV₂ ... UAV_K  (各 UAV 位置均 ???)
```

- **BS** 发射 $N$ 个等角间隔的扫描波束，波束指向未知
- 波束经**粗糙反射面**漫反射后到达 $K$ 个 UAV
- **所有几何量均未知**：BS 位置、波束方向、反射面位置/朝向/法向量、反射点位置、各 UAV 位置（连相对位置也未知）
- **唯一已知**：各 UAV 接收到的 OFDM 多子载波信号，以及 UAV 之间可以相互通信共享数据
- **不依赖** GPS、锚节点、或任何先验位置信息

这是一个**盲几何重建**问题——从分布式接收信号中同时恢复发射源、反射面、和接收端的空间构型。

### 1.2 三层推理链条

```
第一层 [信号 → AoA]  ← 本文档覆盖范围
  接收信号 → SA2N / Grid2N → 每个 UAV 对每个波束的 AoA: (φ̂_{r,n,k}, θ̂_{r,n,k})

第二层 [AoA → 反射点]
  多个 UAV 的 AoA 射线反向交汇 → 同一波束对应的反射点位置 rsp_n

第三层 [反射点 → 反射面 → BS]
  多个反射点拟合反射面 → 法向量 n + 朝向
  入射方向 + 反射面几何 + 出射方向 → BS 位置
```

**本文档覆盖第一层**（信号 → AoA 估计），这是整个盲重建链条中唯一直接与原始数据打交道的算法模块。后续两层依赖于第一层的 AoA 估计精度。

### 1.3 算法验证场景 vs 研究场景

| | 研究场景（目标） | 仿真验证（当前代码） |
|------|------|------|
| BS 位置 | 未知 | 预设坐标 $(0,-10,10)$ |
| 波束方向 | 未知 | 由几何反算 |
| 反射面 | 未知 | 水平面 $(z=0)$，法向量 $[0,0,1]^T$ |
| UAV 位置 | 未知 | 预设坐标 $(0,10,8)$ |
| 子载波数 | $I = 64$ | 同 |
| 阵元数 | $N_r = 64$ | 同 |

仿真验证中预设几何参数仅用于**生成模拟信道数据**和**计算 AoA 估计误差**（作为 ground truth），算法本身**不使用**这些几何先验——它只接收协方差矩阵 $\mathbf{R}_{\mathbf{n,k}}^{(i)}$ 作为输入。

---

## 2. 符号表

> 以下符号完全遵从论文定义。论文未明确定义的参数，以 MATLAB 实现的默认值为准。

### 2.1 几何量

| 符号 | 含义 | 单位/范围 |
|------|------|-----------|
| $\mathbf{p}_b = [x_b, y_b, z_b]^T$ | BS 位置坐标 | m |
| $\mathbf{p}_k = [x_k, y_k, z_k]^T$ | 第 $k$ 个 UAV 位置坐标 | m |
| $\mathbf{rsp}_n = [x_n, y_n, z_n]^T$ | 第 $n$ 个波束对应的反射点坐标 | m |
| $\mathbf{n}$ | 反射面单位法向量，$\|\mathbf{n}\|_2 = 1$ | — |

### 2.2 几何导出量

| 符号 | 定义 | 含义 |
|------|------|------|
| $\mathbf{v}_{n,\text{in}}$ | $\mathbf{rsp}_n - \mathbf{p}_b$ | 入射向量 (BS → 反射点) |
| $\mathbf{v}_{n,k,\text{out}}$ | $\mathbf{p}_k - \mathbf{rsp}_n$ | 出射向量 (反射点 → UAV) |
| $\tau_{n,k}$ | $(\|\mathbf{v}_{n,\text{in}}\| + \|\mathbf{v}_{n,k,\text{out}}\|) / c$ | 路径传播时延 |
| $\mathbf{r}_{n,\text{spec}}$ | $\mathbf{v}_{n,\text{in}} - 2(\mathbf{v}_{n,\text{in}}^T \mathbf{n}) \mathbf{n}$ | 理想镜面反射方向 |
| $\beta_{n,k}$ | $\arccos\!\left(\frac{\mathbf{r}_{n,\text{spec}}^T \mathbf{v}_{n,k,\text{out}}}{\|\mathbf{r}_{n,\text{spec}}\| \|\mathbf{v}_{n,k,\text{out}}\|}\right)$ | 实际散射与镜面方向的夹角 |

### 2.3 角度量

| 符号 | 含义 | 范围 |
|------|------|------|
| $\bm{\Omega}_{n,k} = [\varphi_{r,n,k}, \theta_{r,n,k}]^T$ | 第 $n$ 波束到第 $k$ 个 UAV 的到达角 (AoA) | — |
| $\bm{\theta}_{n,k} = [\varphi_{t,n,k}, \theta_{t,n,k}]^T$ | 第 $n$ 波束的发射角 (AoD) | — |
| $\varphi_{r,n,k}$ | 到达方位角 | $[-\pi, \pi]$ rad |
| $\theta_{r,n,k}$ | 到达俯仰角（与 $+z$ 轴夹角） | $[0, \pi]$ rad |
| $\varphi_{t,n,k}$ | 发射方位角 | $[-\pi, \pi]$ rad |
| $\theta_{t,n,k}$ | 发射俯仰角（与 $+z$ 轴夹角） | $[0, \pi]$ rad |

> :warning: **符号注意**：论文使用 $\bm{\theta}_{n,k}$ 表示 AoD 角度**对**（含方位角和俯仰角两个分量），而标量 $\theta$ 同时用于表示俯仰角。在阅读公式时需根据上下文区分——粗体 $\bm{\theta}$ 为向量，常规体 $\theta$ 为标量俯仰角。

### 2.4 系统参数

| 符号 | 含义 | 默认值 |
|------|------|--------|
| $f_c$ | 载波中心频率 | $28 \times 10^9$ Hz (n257) |
| $c$ | 自由空间光速 | $3 \times 10^8$ m/s |
| $\lambda_c$ | 载波波长 ($c/f_c$) | $\approx 0.0107$ m |
| $\Delta f$ | 子载波间隔 | $120 \times 10^3$ Hz |
| $I$ | 子载波数量 | $64$ |
| $f_i$ | 第 $i$ 个子载波频率 ($f_c + i \cdot \Delta f$) | Hz, $i = 0,\dots,I-1$ |
| $\lambda_i$ | 第 $i$ 个子载波波长 ($c / f_i$) | m |

### 2.5 阵列参数

| 符号 | 含义 | 默认值 |
|------|------|--------|
| $N_{tx}, N_{ty}$ | BS $x$/$y$ 方向阵元数 | $8, 8$ |
| $N_{rx}, N_{ry}$ | UAV $x$/$y$ 方向阵元数 | $8, 8$ |
| $N_t = N_{tx} \times N_{ty}$ | BS 总发射阵元数 | $64$ |
| $N_r = N_{rx} \times N_{ry}$ | UAV 总接收阵元数 | $64$ |
| $d_x, d_y$ | $x$/$y$ 方向阵元间距 | $\lambda_c / 2$（半波长） |

### 2.6 信号与统计算子

| 符号 | 含义 | 默认值/维度 |
|------|------|-------------|
| $M$ | 快拍数（观测符号数） | $50$ |
| $\sigma_s^2$ | 发射信号功率 | $1$ |
| $\sigma_n^2$ | 噪声功率 | 由 SNR 确定 |
| $\alpha = \sigma_s^2 / \sigma_n^2$ | 信噪比（线性） | — |
| $\alpha_R$ | 表面粗糙度指数 | $2$ |
| $\mathbf{a}_{\rm{rx}}^{(i)}(\bm{\Omega})$ | UAV 端接收导向矢量 | $\mathbb{C}^{N_r \times 1}$ |
| $\mathbf{a}_{\rm{tx}}^{(i)}(\bm{\theta})$ | BS 端发射导向矢量 | $\mathbb{C}^{N_t \times 1}$ |
| $\mathbf{H}_{n,k,i}$ | 第 $i$ 子载波的信道矩阵 | $\mathbb{C}^{N_r \times N_t}$ |
| $\mathbf{R}_{\mathbf{n,k}}^{(i)}$ | 第 $i$ 子载波的样本协方差矩阵 | $\mathbb{C}^{N_r \times N_r}$ |
| $J(\bm{\Omega})$ | 空间谱目标函数 | $\mathbb{R}$ |
| $\nabla J$ | 梯度向量 | $\mathbb{R}^{2 \times 1}$ |
| $\mathbf{H}_J$ | 海森矩阵 | $\mathbb{R}^{2 \times 2}$ |

### 2.7 索引约定

| 索引 | 范围 | 含义 |
|------|------|------|
| $n$ | $1, \dots, N$ | 扫描波束编号 |
| $k$ | $1, \dots, K$ | UAV 编号 |
| $i$ | $0, \dots, I-1$ | 子载波编号 |
| $m$ | $1, \dots, M$ | 快拍编号 |

---

## 3. 系统模型

### 3.1 空间几何

BS 发射 $N$ 个等角间隔的扫描波束照射反射面，电磁波经粗糙表面漫反射后到达 $K$ 个 UAV。空间几何由以下向量关系描述：

**入射路径**（BS → 反射点）：

$$
\mathbf{v}_{n,\text{in}} = \mathbf{rsp}_n - \mathbf{p}_b
$$

**出射路径**（反射点 → UAV）：

$$
\mathbf{v}_{n,k,\text{out}} = \mathbf{p}_k - \mathbf{rsp}_n
$$

**传播时延**：

$$
\tau_{n,k} = \frac{\|\mathbf{v}_{n,\text{in}}\| + \|\mathbf{v}_{n,k,\text{out}}\|}{c}
$$

角度由方向向量的球坐标反解得到。以 AoA 为例，定义 UAV 视角的来波方向向量 $\mathbf{u}_{\rm{rx}} = \mathbf{rsp}_n - \mathbf{p}_k$（从 UAV 指向反射点），则：

$$
\boxed{\begin{aligned}
\varphi_{r,n,k} &= \operatorname{atan2}\!\left(\frac{u_{\rm{rx},y}}{\|u_{\rm{rx}}\|}, \frac{u_{\rm{rx},x}}{\|u_{\rm{rx}}\|}\right) \quad \in [-\pi, \pi] \\[4pt]
\theta_{r,n,k} &= \arccos\!\left(\frac{u_{\rm{rx},z}}{\|u_{\rm{rx}}\|}\right) \quad \in [0, \pi]
\end{aligned}}
$$

> **俯仰角约定**：$\theta = 0$ 对应 $+z$ 方向（垂直向上），$\theta = \pi/2$ 对应水平面，$\theta = \pi$ 对应 $-z$ 方向（垂直向下）。

AoD 的推导方式对称，使用 BS 视角的出射方向向量 $\mathbf{v}_{n,\text{in}}$。

### 3.2 阵列拓扑

BS 与 UAV 均配备**均匀平面阵列 (UPA)**，阵元沿 $x$ 和 $y$ 方向以半波长间距均匀排布。

**Kronecker 分解** — 这是 UPA 导向矢量计算的关键性质：

$$
\boxed{\mathbf{a}(\varphi, \theta, \lambda) = \mathbf{a}_y(\varphi, \theta, \lambda) \otimes \mathbf{a}_x(\varphi, \theta, \lambda)}
$$

其中 $x$ 方向和 $y$ 方向的 ULA 导向矢量分别为：

$$
\begin{aligned}
a_{x, n_x}(\varphi, \theta, \lambda) &= \exp\!\left(-j\frac{2\pi}{\lambda} d_x \cdot n_x \cdot \sin\theta \cos\varphi\right), \quad n_x = 0, \dots, N_x-1 \\[4pt]
a_{y, n_y}(\varphi, \theta, \lambda) &= \exp\!\left(-j\frac{2\pi}{\lambda} d_y \cdot n_y \cdot \sin\theta \sin\varphi\right), \quad n_y = 0, \dots, N_y-1
\end{aligned}
$$

> :warning: **对论文的修正 ①**：论文将 UPA 导向矢量写作 $\mathbf{a}_{\rm{rx}} = \mathbf{a}_{\rm{rx}} \otimes \mathbf{a}_{\rm{ry}}$，其中符号 $\mathbf{a}_{\rm{rx}}$ 在等式两侧含义不同（左侧为全阵矢量，右侧为 $x$ 方向子阵矢量），且 Kronecker 积的顺序应为 $\mathbf{a}_y \otimes \mathbf{a}_x$ 而非 $\mathbf{a}_x \otimes \mathbf{a}_y$。本文档已修正。详见 [§11](#11-论文问题与修正)。

**阵元索引映射** — 用于梯度/海森矩阵的紧凑计算。定义两个索引向量：

$$
\begin{aligned}
m_x &= [0, 1, \dots, N_{rx}-1]^T \otimes \mathbf{1}_{N_{ry}} \quad \in \mathbb{R}^{N_r \times 1} \\[4pt]
m_y &= \mathbf{1}_{N_{rx}} \otimes [0, 1, \dots, N_{ry}-1]^T \quad \in \mathbb{R}^{N_r \times 1}
\end{aligned}
$$

由此，导向矢量可紧凑地写为逐元素指数形式：

$$
\boxed{\mathbf{a}(\varphi, \theta, \lambda) = \exp\!\left[-j\frac{2\pi}{\lambda}\Big(m_x d_x \sin\theta \cos\varphi + m_y d_y \sin\theta \sin\varphi\Big)\right]}
$$

此形式避免了显式的 Kronecker 积展开，在梯度推导中尤为方便。

### 3.3 漫反射衰减模型

粗糙表面使入射电磁波向四周散射，实际出射方向的功率取决于其偏离理想镜面反射方向的程度。采用 **Phong 漫反射模型**的经验推广：

$$
\boxed{\Gamma(\beta_{n,k}) = \left(\frac{1 + \cos\beta_{n,k}}{2}\right)^{\frac{\alpha_R}{2}}}
$$

| 参数 | 物理含义 | 取值 |
|------|----------|------|
| $\beta_{n,k}$ | 实际出射方向 $\mathbf{v}_{n,k,\text{out}}$ 与镜面方向 $\mathbf{r}_{n,\text{spec}}$ 的夹角 | 由几何决定 |
| $\alpha_R$ | 表面粗糙度指数，越大衰减越剧烈 | $2$（默认） |
| $\Gamma(\beta_{n,k})$ | 漫反射功率保留因子 | $[0, 1]$ |

> 当 $\beta_{n,k} = 0$（恰好是镜面方向）时 $\Gamma = 1$，对应理想反射。$\beta_{n,k}$ 增大时 $\Gamma$ 迅速衰减。

---

## 4. 信号模型

### 4.1 OFDM 子载波结构

系统采用 OFDM 调制，$I$ 个子载波均匀分布于载频 $f_c$ 两侧：

$$
f_i = f_c + i \cdot \Delta f, \quad i = 0, 1, \dots, I-1
$$

$$
\lambda_i = \frac{c}{f_i}
$$

| 参数 | 值 | 说明 |
|------|-----|------|
| $f_c$ | 28 GHz | n257 毫米波频段 |
| $\Delta f$ | 120 kHz | 子载波间隔 |
| $I$ | 64 | 子载波数 |
| 总带宽 | $I \cdot \Delta f = 7.68$ MHz | 窄带假设在各子载波上成立 |

> 不同子载波经历相同的空间角度（窄带假设），但相位响应 $e^{-j 2\pi f_i \tau}$ 随频率变化。联合处理多子载波可提升 AoA 估计精度。

### 4.2 导向矢量

**BS 发射导向矢量**（$N_t \times 1$，方向 $\bm{\theta}_{n,k}$）：

$$
\mathbf{a}_{\rm{tx}}^{(i)}(\bm{\theta}_{n,k}) = \exp\!\left[-j\frac{2\pi}{\lambda_i}\Big(m_{\rm{tx},x} d_x \sin\theta_{t,n,k} \cos\varphi_{t,n,k} + m_{\rm{tx},y} d_y \sin\theta_{t,n,k} \sin\varphi_{t,n,k}\Big)\right]
$$

**UAV 接收导向矢量**（$N_r \times 1$，方向 $\bm{\Omega}_{n,k}$）：

$$
\boxed{\mathbf{a}_{\rm{rx}}^{(i)}(\bm{\Omega}_{n,k}) = \exp\!\left[-j\frac{2\pi}{\lambda_i}\Big(m_{\rm{rx},x} d_x \sin\theta_{r,n,k} \cos\varphi_{r,n,k} + m_{\rm{rx},y} d_y \sin\theta_{r,n,k} \sin\varphi_{r,n,k}\Big)\right]}
$$

### 4.3 信道矩阵

对于第 $i$ 个子载波、第 $n$ 个波束到第 $k$ 个 UAV 的链路，窄带频域信道矩阵 $\mathbf{H}_{n,k,i} \in \mathbb{C}^{N_r \times N_t}$ 为：

$$
\boxed{\mathbf{H}_{n,k,i} = \underbrace{\left(\frac{1+\cos\beta_{n,k}}{2}\right)^{\frac{\alpha_R}{2}}}_{\Gamma(\beta_{n,k})} \cdot\; \underbrace{e^{-j 2\pi f_i \tau_{n,k}}}_{\text{相位旋转}} \cdot\; \mathbf{a}_{\rm{rx}}^{(i)}(\bm{\Omega}_{n,k}) \cdot \underbrace{\left[\mathbf{a}_{\rm{tx}}^{(i)}(\bm{\theta}_{n,k})\right]^H}_{\text{BS 端共轭转置}}}
$$

此信道矩阵 **秩为 1**（单主径漫反射假设）。在高频段（28 GHz），漫反射虽使能量衰减但不改变几何光学决定的出射角度，秩-1 近似合理。

### 4.4 接收信号与协方差矩阵

**发射端波束成形**：BS 对第 $n$ 个波束使用 MRT（最大比传输），波束成形向量即导向矢量本身：

$$
\mathbf{w}_{\rm{tx}}^{(i)} = \mathbf{a}_{\rm{tx}}^{(i)}(\bm{\theta}_{n,k})
$$

发射符号 $s_{n,i,m} \sim \mathcal{CN}(0, \sigma_s^2)$，$\sigma_s^2 = 1$。

**接收端**：第 $k$ 个 UAV、第 $m$ 个快拍的接收信号向量（$N_r \times 1$）：

$$
\mathbf{r}_{n,k,i,m} = \mathbf{H}_{n,k,i} \, \mathbf{a}_{\rm{tx}}^{(i)}(\bm{\theta}_{n,k}) \, s_{n,i,m} + \bm{\omega}_{n,k,i,m}
$$

其中 $\bm{\omega}_{n,k,i,m} \sim \mathcal{CN}(\mathbf{0}, \sigma_n^2 \mathbf{I}_{N_r})$ 为加性复高斯白噪声。

**样本协方差矩阵** — 算法的**唯一输入数据**：

收集 $M$ 个快拍，对每个子载波 $i$ 构建：

$$
\boxed{\mathbf{R}_{\mathbf{n,k}}^{(i)} = \frac{1}{M} \sum_{m=1}^{M} \mathbf{r}_{n,k,i,m} \, \mathbf{r}_{n,k,i,m}^H \quad \in \mathbb{C}^{N_r \times N_r}}
$$

算法实际操作的是**多子载波协方差张量**：

$$
\mathcal{R}_{\mathbf{n,k}} = \left\{\mathbf{R}_{\mathbf{n,k}}^{(i)}\right\}_{i=0}^{I-1} \quad \in \mathbb{C}^{N_r \times N_r \times I}
$$

> **为什么用协方差矩阵而非原始快拍？** 协方差矩阵的秩与特征值分布编码了信号子空间的几何结构，在低 SNR 下比单快拍提供更稳健的统计信息。

---

## 5. 最大似然 AoA 估计框架

### 5.1 似然函数推导

本节复现论文中从贝叶斯后验到 $J(\bm{\Omega})$ 目标函数的完整推导链。

**步骤 1 — 后验与先验**：

$$
p(\bm{\Omega}_{n,k} \mid \mathbf{R}_{n,k,i}) \propto p(\mathbf{R}_{n,k,i} \mid \bm{\Omega}_{n,k}) \cdot p(\bm{\Omega}_{n,k})
$$

由于波束扫描方向可控，$p(\bm{\Omega}_{n,k})$ 可近似为均匀分布，后验等价于似然：

$$
p(\bm{\Omega}_{n,k} \mid \mathbf{R}_{n,k,i}) \propto p(\mathbf{R}_{n,k,i} \mid \bm{\Omega}_{n,k})
$$

**步骤 2 — 联合似然因子分解**：$M$ 个快拍相互独立，且各快拍对 $s$ 积分后得：

$$
p(\mathbf{R}_{n,k,i} \mid \bm{\Omega}_{n,k}) = \prod_{m=1}^{M} \int p(\mathbf{r}_{n,k,i,m} \mid \bm{\Omega}_{n,k}, s) \; p(s) \; ds
$$

**步骤 3 — 单快拍似然积分**：代入 $s \sim \mathcal{CN}(0, \sigma_s^2)$ 和复高斯噪声假设，完成高斯积分。经过矩阵代数整理后得到简洁形式：

$$
p(\mathbf{r}_{n,k,i,m} \mid \bm{\Omega}_{n,k}) = \frac{1}{\pi^{N_r} \det(\mathbf{C}(\bm{\Omega}_{n,k}))} \exp\!\left(-\mathbf{r}_{n,k,i,m}^H \mathbf{C}(\bm{\Omega}_{n,k})^{-1} \mathbf{r}_{n,k,i,m}\right)
$$

其中：

$$
\mathbf{C}(\bm{\Omega}_{n,k}) = \sigma_n^2 \mathbf{I}_{N_r} + \sigma_s^2 \, \mathbf{a}_{\rm{rx}}(\bm{\Omega}_{n,k}) \, \mathbf{a}_{\rm{rx}}^H(\bm{\Omega}_{n,k})
$$

**步骤 4 — 对数似然**：对 $M$ 个快拍取对数并平均：

$$
\begin{aligned}
\mathcal{L}(\sigma_n^2, \sigma_s^2, \bm{\Omega}_{n,k}) &= \frac{1}{M} \sum_{m=1}^{M} \log p(\mathbf{r}_{n,k,i,m} \mid \bm{\Omega}_{n,k}) \\[4pt]
&= -N_r \log \sigma_n^2 - \log(1 + \alpha g(\bm{\Omega}_{n,k})) \\
&\quad + \frac{1}{\sigma_n^2}\left(\operatorname{tr}(\mathbf{R}_{\mathbf{n,k}}^{(i)}) - \frac{\alpha \, q(\bm{\Omega}_{n,k})}{1 + \alpha g(\bm{\Omega}_{n,k})}\right)
\end{aligned}
$$

其中引入了两个辅助函数：

$$
\boxed{\begin{aligned}
g(\bm{\Omega}_{n,k}) &\triangleq \mathbf{a}_{\rm{rx}}^H(\bm{\Omega}_{n,k}) \, \mathbf{a}_{\rm{rx}}(\bm{\Omega}_{n,k}) = N_r \\[4pt]
q(\bm{\Omega}_{n,k}) &\triangleq \mathbf{a}_{\rm{rx}}^H(\bm{\Omega}_{n,k}) \, \mathbf{R}_{\mathbf{n,k}}^{(i)} \, \mathbf{a}_{\rm{rx}}(\bm{\Omega}_{n,k})
\end{aligned}}
$$

以及 $\alpha = \sigma_s^2 / \sigma_n^2$（信噪比线性值）。

### 5.2 未知参数闭式解

$\sigma_n^2$ 和 $\sigma_s^2$ 在实际中未知。对 $\mathcal{L}$ 分别求偏导并置零：

$$
\begin{aligned}
\frac{\partial \mathcal{L}}{\partial \sigma_n^2} &= \frac{N_r}{\sigma_n^2} - \frac{1}{\sigma_n^4}\left(\operatorname{tr}(\mathbf{R}_{\mathbf{n,k}}^{(i)}) - \frac{\alpha \, q(\bm{\Omega})}{1 + \alpha N_r}\right) = 0 \\[6pt]
\frac{\partial \mathcal{L}}{\partial \alpha} &= \frac{N_r}{1 + \alpha N_r} - \frac{q(\bm{\Omega})}{\sigma_n^2 (1 + \alpha N_r)^2} = 0
\end{aligned}
$$

联立解得闭式表达式：

$$
\boxed{\begin{aligned}
\sigma_n^2 &= \frac{\operatorname{tr}(\mathbf{R}_{\mathbf{n,k}}^{(i)}) - J^{(i)}(\bm{\Omega}_{n,k})}{N_r - 1} \\[8pt]
\sigma_s^2 &= \frac{N_r J^{(i)}(\bm{\Omega}_{n,k}) - \operatorname{tr}(\mathbf{R}_{\mathbf{n,k}}^{(i)})}{(N_r - 1) N_r}
\end{aligned}}
$$

### 5.3 目标函数与优化问题

定义**归一化空间谱能量**：

$$
\boxed{J^{(i)}(\bm{\Omega}_{n,k}) = \frac{q(\bm{\Omega}_{n,k})}{g(\bm{\Omega}_{n,k})} = \frac{1}{N_r} \, \mathbf{a}_{\rm{rx}}^H(\bm{\Omega}_{n,k}) \, \mathbf{R}_{\mathbf{n,k}}^{(i)} \, \mathbf{a}_{\rm{rx}}(\bm{\Omega}_{n,k})}
$$

将 $\sigma_n^2$ 和 $\sigma_s^2$ 代回对数似然，得到仅依赖 $J^{(i)}$ 的形式：

$$
\mathcal{L}(\bm{\Omega}_{n,k}) = -(N_r - 1) \log\!\left(\operatorname{tr}(\mathbf{R}_{\mathbf{n,k}}^{(i)}) - J^{(i)}\right) - \log J^{(i)} - C
$$

其中 $C$ 为常数。

**单调性保证**：当 $N_r > 1$ 时有 $N_r J^{(i)} > \operatorname{tr}(\mathbf{R}_{\mathbf{n,k}}^{(i)})$（信号子空间功率大于噪声平均功率），导数：

$$
\frac{\partial \mathcal{L}}{\partial J^{(i)}} = \frac{N_r J^{(i)} - \operatorname{tr}(\mathbf{R}_{\mathbf{n,k}}^{(i)})}{J^{(i)} \left(\operatorname{tr}(\mathbf{R}_{\mathbf{n,k}}^{(i)}) - J^{(i)}\right)} > 0
$$

严格单调递增。**因此最大化对数似然 $\mathcal{L}$ 等价于最大化 $J^{(i)}$**。AoA 估计问题最终化为：

$$
\boxed{\hat{\bm{\Omega}}_{n,k} = \arg\max_{\bm{\Omega}} \; J^{(i)}(\bm{\Omega})}
$$

这是 $\varphi \in [-\pi, \pi], \theta \in [0, \pi]$ 上的 **2D 无约束非凸优化**——$J$ 在角度域存在多个旁瓣（局部极值），需要高效的全局优化策略。

### 5.4 多子载波扩展

论文推导基于单子载波 $i$。在 OFDM 系统中，$I$ 个子载波经历相同的空间角度，联合处理可提升估计稳健性。将目标函数扩展为 $I$ 个子载波的算术平均：

$$
\boxed{J(\bm{\Omega}) = \frac{1}{I} \sum_{i=0}^{I-1} J^{(i)}(\bm{\Omega}) = \frac{1}{N_r I} \sum_{i=0}^{I-1} \mathbf{a}_{\rm{rx}}^H(\bm{\Omega}, \lambda_i) \; \mathbf{R}_{\mathbf{n,k}}^{(i)} \; \mathbf{a}_{\rm{rx}}(\bm{\Omega}, \lambda_i)}
$$

> 由于单调性在每个子载波上独立成立，对 $J^{(i)}$ 的凸组合（算术平均）保留相同的 argmax 性质。MATLAB 实现采用此多子载波形式。

---

## 6. SA2N 算法

SA2N (Simulated Annealing → Newton) 是一种**两级混合优化**策略：

- **第一级**：模拟退火 (SA) 做全局概率搜索，定位主瓣区域
- **第二级**：牛顿-拉夫逊 (NR) 做局部二阶收敛，达到高精度解

### 6.1 阶段一：模拟退火

| 参数 | 取值 | 含义 |
|------|------|------|
| $T_0$ | $100$ | 初始温度 |
| $T_{\min}$ | $1$ | 终止温度 |
| $\rho$ | $0.85$ | 降温因子 $(T \leftarrow \rho \cdot T)$ |
| $K_{\text{SA}}$ | $10$ | 每温度下迭代次数 |

**算法流程**：

1. **初始化**：随机采样 $\varphi_{\text{curr}} \sim \mathcal{U}(-\pi, \pi)$，$\theta_{\text{curr}} \sim \mathcal{U}(0, \pi)$，计算 $J_{\text{curr}} = J(\varphi_{\text{curr}}, \theta_{\text{curr}})$

2. **内循环**（温度 $T$ 下重复 $K_{\text{SA}}$ 次）：
   
   在当前点附近按温度比例随机扰动：
   $$
   \begin{aligned}
   \Delta\varphi &\sim \mathcal{N}\!\left(0, \tfrac{T}{100} \times 0.5\right) \\
   \Delta\theta &\sim \mathcal{N}\!\left(0, \tfrac{T}{100} \times 0.5\right) \\[4pt]
   \varphi_{\text{new}} &= \operatorname{wrapToPi}(\varphi_{\text{curr}} + \Delta\varphi) \\
   \theta_{\text{new}} &= \max(0, \min(\pi, \theta_{\text{curr}} + \Delta\theta))
   \end{aligned}
   $$
   
   计算 $\Delta J = J_{\text{new}} - J_{\text{curr}}$
   
   **Metropolis 准则**：
   $$
   P_{\text{accept}} = \begin{cases}
   1, & \Delta J > 0 \\[4pt]
   \exp\!\left(\dfrac{\Delta J}{0.1 \cdot T}\right), & \Delta J \le 0
   \end{cases}
   $$

3. **降温**：$T \leftarrow \rho \cdot T$，若 $T > T_{\min}$ 则回到步骤 2

4. **输出粗估计**：$\tilde{\bm{\Omega}}^{(0)} = [\varphi_{\text{SA}}, \theta_{\text{SA}}]^T$

### 6.2 阶段二：牛顿-拉夫逊迭代

以 SA 粗估计 $\tilde{\bm{\Omega}}^{(0)}$ 为初始点，利用目标函数的二阶信息快速收敛到精确解：

$$
\boxed{\tilde{\bm{\Omega}}^{(t+1)} = \tilde{\bm{\Omega}}^{(t)} - \mathbf{H}_J^{-1}\!\left(\tilde{\bm{\Omega}}^{(t)}\right) \cdot \nabla J\!\left(\tilde{\bm{\Omega}}^{(t)}\right)}
$$

其中：

$$
\tilde{\bm{\Omega}} = \begin{bmatrix} \varphi \\ \theta \end{bmatrix}, \quad
\nabla J = \begin{bmatrix} \dfrac{\partial J}{\partial \varphi} \\[8pt] \dfrac{\partial J}{\partial \theta} \end{bmatrix}, \quad
\mathbf{H}_J = \begin{bmatrix} \dfrac{\partial^2 J}{\partial \varphi^2} & \dfrac{\partial^2 J}{\partial \varphi \partial \theta} \\[8pt] \dfrac{\partial^2 J}{\partial \theta \partial \varphi} & \dfrac{\partial^2 J}{\partial \theta^2} \end{bmatrix}
$$

**终止条件**：

$$
\|\Delta\tilde{\bm{\Omega}}\|_2 < 10^{-5} \quad \text{或} \quad t \ge 20
$$

**角度约束**（每步迭代后）：

$$
\varphi^{(t)} \leftarrow \operatorname{wrapToPi}(\varphi^{(t)}), \qquad
\theta^{(t)} \leftarrow \max(0, \min(\pi, \theta^{(t)}))
$$

---

## 7. Grid2N 算法

Grid2N (Grid Search → Multi-start Newton) 采用 **三级策略**，以确定性的网格搜索替代 SA 的随机探索：

### 7.1 阶段一：均匀网格采样

| 参数 | 取值 | 设计依据 |
|------|------|----------|
| $\Delta_{\text{grid}}$ | $10^\circ$ ($\approx 0.175$ rad) | $8\times 8$ UPA 主瓣 3dB 宽度 $\sim 12^\circ$，$10^\circ$ 步长保证不漏瓣 |

- 方位角：$\varphi_{\text{grid}} \in \{-180^\circ, -170^\circ, \dots, 180^\circ\}$（37 点）
- 俯仰角：$\theta_{\text{grid}} \in \{0^\circ, 10^\circ, \dots, 180^\circ\}$（19 点）
- 总计：$37 \times 19 = 703$ 个候选方向

对每个网格点计算 $J(\varphi, \theta)$ 得到 2D 空间谱矩阵 $\mathbf{J}_{\text{surf}} \in \mathbb{R}^{19 \times 37}$。

### 7.2 阶段二：Top-N 峰值提取

从 $703$ 个网格点中提取 $N_{\text{peaks}} = 3$ 个相互独立的局部峰值作为牛顿法的多起始点。

| 参数 | 取值 | 含义 |
|------|------|------|
| $N_{\text{peaks}}$ | $3$ | 保留的候选峰值数 |
| $d_{\min}$ | $15^\circ$ ($\approx 0.262$ rad) | 候选点间最小角距离（非极大值抑制半径） |

**角距离**（近似 Euclidean）：

$$
d_{\text{angular}}(\bm{\Omega}_1, \bm{\Omega}_2) = \sqrt{\left|\operatorname{wrapToPi}(\varphi_1 - \varphi_2)\right|^2 + |\theta_1 - \theta_2|^2}
$$

**提取流程**：

1. 将 $\mathbf{J}_{\text{surf}}$ 按能量从大到小排序
2. 依次遍历：若当前候选与所有已选点的角距离均 $\ge d_{\min}$，则保留
3. 达到 $N_{\text{peaks}}$ 个后停止

### 7.3 阶段三：多起始点牛顿精炼

对 $N_{\text{peaks}}$ 个候选峰值，各自运行牛顿迭代（与 [§6.2](#62-阶段二牛顿-拉夫逊迭代) 相同），得到收敛点集 $\{\bm{\Omega}_p^{\text{final}}\}_{p=1}^{N_{\text{peaks}}}$。选取最终 $J$ 值最大者：

$$
\hat{\bm{\Omega}}_{n,k} = \arg\max_{p=1,\dots,N_{\text{peaks}}} J\!\left(\bm{\Omega}_p^{\text{final}}\right)
$$

### 7.4 两算法对比

| 维度 | SA2N | Grid2N |
|------|------|--------|
| 全局探索方式 | 随机（SA 概率游走） | 确定性（均匀网格） |
| $J$ 评估次数 | $\sim 290$（SA 阶段） | $703$（网格阶段） |
| 牛顿初始点 | 1 个（SA 终态） | $N_{\text{peaks}} = 3$ 个 |
| 优势 | 可自适应调整搜索密度 | 覆盖全面、不漏瓣 |
| 风险 | 可能未探索到全局最优区域 | 网格步长固定、计算量较大 |

---

## 8. 梯度与海森矩阵

> 本节给出 $J(\bm{\Omega})$ 的一阶和二阶偏导闭式表达式。闭式计算避免了有限差分的步长敏感性和额外的 $J$ 评估开销。

### 8.1 辅助变量

对第 $i$ 个子载波，定义相位偏移向量：

$$
\boldsymbol{\mu}^{(i)}(\varphi, \theta) = \frac{2\pi}{\lambda_i}\Big(m_x d_x \sin\theta \cos\varphi + m_y d_y \sin\theta \sin\varphi\Big) \quad \in \mathbb{R}^{N_r \times 1}
$$

则导向矢量为 $\mathbf{a}^{(i)} = e^{-j\boldsymbol{\mu}^{(i)}}$（逐元素指数）。

**$\boldsymbol{\mu}$ 的一阶偏导**：

$$
\boxed{\begin{aligned}
\boldsymbol{\mu}_\varphi^{(i)} &\triangleq \frac{\partial \boldsymbol{\mu}^{(i)}}{\partial \varphi} = \frac{2\pi}{\lambda_i}\Big(-m_x d_x \sin\theta \sin\varphi + m_y d_y \sin\theta \cos\varphi\Big) \\[6pt]
\boldsymbol{\mu}_\theta^{(i)} &\triangleq \frac{\partial \boldsymbol{\mu}^{(i)}}{\partial \theta} = \frac{2\pi}{\lambda_i}\Big(m_x d_x \cos\theta \cos\varphi + m_y d_y \cos\theta \sin\varphi\Big)
\end{aligned}}
$$

**$\boldsymbol{\mu}$ 的二阶偏导**：

$$
\boxed{\begin{aligned}
\boldsymbol{\mu}_{\varphi\varphi}^{(i)} &= -\boldsymbol{\mu}^{(i)} \\[4pt]
\boldsymbol{\mu}_{\theta\theta}^{(i)} &= -\boldsymbol{\mu}^{(i)} \\[4pt]
\boldsymbol{\mu}_{\varphi\theta}^{(i)} &= \frac{2\pi}{\lambda_i}\Big(-m_x d_x \cos\theta \sin\varphi + m_y d_y \cos\theta \cos\varphi\Big)
\end{aligned}}
$$

### 8.2 导向矢量的偏导

**一阶**：

$$
\frac{\partial \mathbf{a}^{(i)}}{\partial \varphi} = -j \boldsymbol{\mu}_\varphi^{(i)} \odot \mathbf{a}^{(i)}, \qquad
\frac{\partial \mathbf{a}^{(i)}}{\partial \theta} = -j \boldsymbol{\mu}_\theta^{(i)} \odot \mathbf{a}^{(i)}
$$

**二阶**：

$$
\boxed{\begin{aligned}
\frac{\partial^2 \mathbf{a}^{(i)}}{\partial \varphi^2} &= \Big(-j \boldsymbol{\mu}_{\varphi\varphi}^{(i)} - [\boldsymbol{\mu}_\varphi^{(i)}]^{\circ 2}\Big) \odot \mathbf{a}^{(i)} \\[6pt]
\frac{\partial^2 \mathbf{a}^{(i)}}{\partial \theta^2} &= \Big(-j \boldsymbol{\mu}_{\theta\theta}^{(i)} - [\boldsymbol{\mu}_\theta^{(i)}]^{\circ 2}\Big) \odot \mathbf{a}^{(i)} \\[6pt]
\frac{\partial^2 \mathbf{a}^{(i)}}{\partial \varphi \partial \theta} &= \Big(-j \boldsymbol{\mu}_{\varphi\theta}^{(i)} - \boldsymbol{\mu}_\varphi^{(i)} \odot \boldsymbol{\mu}_\theta^{(i)}\Big) \odot \mathbf{a}^{(i)}
\end{aligned}}
$$

其中 $[\mathbf{x}]^{\circ 2}$ 表示逐元素平方（Hadamard 平方）。

### 8.3 梯度向量 $\nabla J$

$$
\boxed{\begin{aligned}
\frac{\partial J}{\partial \varphi} &= \frac{2}{N_r I} \sum_{i=0}^{I-1} \Re\!\left\{ \left[\mathbf{a}^{(i)}\right]^H \mathbf{R}^{(i)} \frac{\partial \mathbf{a}^{(i)}}{\partial \varphi} \right\} \\[8pt]
\frac{\partial J}{\partial \theta} &= \frac{2}{N_r I} \sum_{i=0}^{I-1} \Re\!\left\{ \left[\mathbf{a}^{(i)}\right]^H \mathbf{R}^{(i)} \frac{\partial \mathbf{a}^{(i)}}{\partial \theta} \right\}
\end{aligned}}
$$

### 8.4 海森矩阵 $\mathbf{H}_J$

$\mathbf{H}_J \in \mathbb{R}^{2 \times 2}$ 对称。各元素为：

$$
\boxed{\begin{aligned}
H_{11} &= \frac{2}{N_r I} \sum_{i=0}^{I-1} \Re\!\left\{ \left(\frac{\partial \mathbf{a}^{(i)}}{\partial \varphi}\right)^H \mathbf{R}^{(i)} \frac{\partial \mathbf{a}^{(i)}}{\partial \varphi} + \left[\mathbf{a}^{(i)}\right]^H \mathbf{R}^{(i)} \frac{\partial^2 \mathbf{a}^{(i)}}{\partial \varphi^2} \right\} \\[8pt]
H_{22} &= \frac{2}{N_r I} \sum_{i=0}^{I-1} \Re\!\left\{ \left(\frac{\partial \mathbf{a}^{(i)}}{\partial \theta}\right)^H \mathbf{R}^{(i)} \frac{\partial \mathbf{a}^{(i)}}{\partial \theta} + \left[\mathbf{a}^{(i)}\right]^H \mathbf{R}^{(i)} \frac{\partial^2 \mathbf{a}^{(i)}}{\partial \theta^2} \right\} \\[8pt]
H_{12} = H_{21} &= \frac{2}{N_r I} \sum_{i=0}^{I-1} \Re\!\left\{ \left(\frac{\partial \mathbf{a}^{(i)}}{\partial \varphi}\right)^H \mathbf{R}^{(i)} \frac{\partial \mathbf{a}^{(i)}}{\partial \theta} + \left[\mathbf{a}^{(i)}\right]^H \mathbf{R}^{(i)} \frac{\partial^2 \mathbf{a}^{(i)}}{\partial \varphi \partial \theta} \right\}
\end{aligned}}
$$

> **计算复杂度**：每次 $\nabla J$ 和 $\mathbf{H}_J$ 的联合计算为 $O(I \cdot N_r^2)$，与两次 $J$ 评估的成本相当。在 64 阵元、64 子载波的配置下约为 $O(2.6 \times 10^5)$ 次复数乘加，在现代 CPU 上可忽略不计。

---

## 9. 坐标系转换：LCS → GCS

UAV 安装在运动平台（如无人机）上时，阵列的**局部坐标系 (LCS)** 与**全局物理坐标系 (GCS)** 可能不一致。算法估计的 AoA 定义在 LCS 中，需要根据 UAV 的姿态角转换到统一的 GCS。

### 9.1 Z-Y-X 欧拉角旋转矩阵

给定 UAV 的 Roll ($\alpha$)、Pitch ($\beta$)、Yaw ($\gamma$)：

$$
\begin{aligned}
\mathbf{R}_x(\alpha) &= \begin{bmatrix} 1 & 0 & 0 \\ 0 & \cos\alpha & -\sin\alpha \\ 0 & \sin\alpha & \cos\alpha \end{bmatrix} \quad \text{(绕 x)} \\[8pt]
\mathbf{R}_y(\beta)  &= \begin{bmatrix} \cos\beta & 0 & \sin\beta \\ 0 & 1 & 0 \\ -\sin\beta & 0 & \cos\beta \end{bmatrix} \quad \text{(绕 y)} \\[8pt]
\mathbf{R}_z(\gamma) &= \begin{bmatrix} \cos\gamma & -\sin\gamma & 0 \\ \sin\gamma & \cos\gamma & 0 \\ 0 & 0 & 1 \end{bmatrix} \quad \text{(绕 z)}
\end{aligned}
$$

组合旋转（Roll → Pitch → Yaw）：

$$
\boxed{\mathbf{R}_{\rm{bg}} = \mathbf{R}_z(\gamma) \cdot \mathbf{R}_y(\beta) \cdot \mathbf{R}_x(\alpha) \quad \in \mathbb{R}^{3 \times 3}}
$$

### 9.2 角度转换

1. **LCS 方向余弦**：

   $$
   \mathbf{u}_{\text{LCS}} = \begin{bmatrix} \sin\hat{\theta}_{\text{LCS}} \cos\hat{\varphi}_{\text{LCS}} \\ \sin\hat{\theta}_{\text{LCS}} \sin\hat{\varphi}_{\text{LCS}} \\ \cos\hat{\theta}_{\text{LCS}} \end{bmatrix}
   $$

2. **旋转**：$\mathbf{u}_{\text{GCS}} = \mathbf{R}_{\rm{bg}} \cdot \mathbf{u}_{\text{LCS}}$

3. **GCS 角度反解**：

   $$
   \hat{\varphi}_{\text{GCS}} = \operatorname{atan2}(u_{\text{GCS},y},\; u_{\text{GCS},x}), \qquad
   \hat{\theta}_{\text{GCS}} = \arccos(u_{\text{GCS},z})
   $$

### 9.3 误差计算

**方位角**（处理 $\pm\pi$ 周期跳变）：

$$
\varepsilon_\varphi = \left|\operatorname{wrapToPi}(\varphi_{\text{true}} - \hat{\varphi}_{\text{GCS}})\right| \times \frac{180^\circ}{\pi}
$$

**俯仰角**：

$$
\varepsilon_\theta = \left|\theta_{\text{true}} - \hat{\theta}_{\text{GCS}}\right| \times \frac{180^\circ}{\pi}
$$

---

## 10. 算法在盲几何重建中的角色

### 10.1 输入输出

| | 内容 |
|------|------|
| **输入** | 协方差张量 $\mathcal{R}_{\mathbf{n,k}} \in \mathbb{C}^{N_r \times N_r \times I}$（纯信号域数据，不含任何几何先验） |
| **输出** | AoA 估计 $\hat{\bm{\Omega}}_{n,k} = [\hat{\varphi}_{r,n,k}, \hat{\theta}_{r,n,k}]^T$（LCS 下定义） |

### 10.2 在整个研究链条中的位置

```
第一层 [信号 → 角度 + 时延 + 能量]
  ├── 1a. AoA 估计     ← 本文档 (SA2N / Grid2N)
  │    输入: 协方差张量 R^{(i)}
  │    输出: AoA 估计 {φ̂_{r,n,k}, θ̂_{r,n,k}} + 噪声功率 σ_n^2
  │
  ├── 1b. TDOA 估计    ← TDOA_Estimation_Algorithm.md
  │    输入: 协方差张量 + AoA → 空间滤波 → 互功率谱 WLS
  │    输出: TDOA {Δτ̂_{n,k,1}} + DDOA {Δd̂_{n,k,1}}
  │
  └── 1c. 漫反射参数估计 ← Reflection_Parameter_Estimation.md
       输入: 波束成形标量信号 + AoA + σ_n^2 + DDOA
       输出: 镜面方向 {r̂_{spec,n}} + 粗糙度 α̂_R

第二层 [角度 + 时延 + 能量 → 反射点 + UAV 相对位置]
  联合 AoA 方向 + DDOA 双曲面 + 镜面方向约束
  → 反射点 {rsp_n} + UAV 坐标 {p_k}

第三层 [反射点 → 反射面 → BS]
  多反射点 + 多镜面方向 → 法向量 n
  镜面反射定律 → 入射方向 → BS 位置
```

### 10.3 算法验证策略

当前 MATLAB 代码在**仿真验证场景**中运行（预设几何参数用于生成模拟信道数据），但算法本身是**盲的**——不依赖任何几何先验：

1. 用预设坐标生成物理信道（产生 ground truth AoA）
2. 从信道生成接收信号 → 构建协方差矩阵
3. 将协方差矩阵送入 SA2N / Grid2N 进行 AoA 估计
4. 将估计 AoA 与 ground truth 对比，计算误差

这种验证方式保证了算法在真实盲场景中的可用性——只要接收信号的信道符合漫反射 + UPA 模型，算法就能输出高精度 AoA 估计，为后续的几何重建提供可靠输入。

---

## 11. 论文问题与修正

以下列出论文中存在的笔误、歧义或不一致之处，以及本文档中的对应修正。

### :warning: 11.1 UPA 导向矢量的 Kronecker 积

**原文**（System Model）：
$$
\mathbf{a}_{\rm{rx}}(\bm{\Omega}_{n,k}) = \mathbf{a}_{\rm{rx}}(\varphi_{r,n,k}, \theta_{r,n,k}) \otimes \mathbf{a}_{\rm{ry}}(\varphi_{r,n,k}, \theta_{r,n,k})
$$

以及：
$$
\mathbf{a}_{\rm{tx}}^{H}(\bm{\theta}_{n,k}) = \mathbf{a}_{\rm{tx}}(\varphi_{t,n,k}, \theta_{t,n,k}) \otimes \mathbf{a}_{\rm{ty}}(\varphi_{t,n,k}, \theta_{t,n,k})
$$

**问题**：

1. **符号歧义**：$\mathbf{a}_{\rm{rx}}$ 同时出现在等式左侧（全阵 $N_r \times 1$ 矢量）和右侧第一個因子（$x$ 方向 $N_{rx} \times 1$ 矢量子），同一符号表示两个不同的量。

2. **Kronecker 积顺序**：UPA 导向矢量的标准分解为 $\mathbf{a}_y \otimes \mathbf{a}_x$（即 $y$ 方向在前，$x$ 方向在后，等价于先行后列展开）。论文写成 $\mathbf{a}_{\rm{rx}} \otimes \mathbf{a}_{\rm{ry}}$（$x$ 在前）与 MATLAB 实现 `kron(a_rx_y, a_rx_x)` 矛盾。

**修正**：

将 $x$ 和 $y$ 方向子阵矢量分别记为：

$$
\begin{aligned}
\mathbf{a}_{\rm{rx},x}^{(i)}(\bm{\Omega}) &\in \mathbb{C}^{N_{rx} \times 1} \quad \text{(x 方向)} \\[4pt]
\mathbf{a}_{\rm{rx},y}^{(i)}(\bm{\Omega}) &\in \mathbb{C}^{N_{ry} \times 1} \quad \text{(y 方向)}
\end{aligned}
$$

则 UPA 全阵导向矢量为：

$$
\boxed{\mathbf{a}_{\rm{rx}}^{(i)}(\bm{\Omega}) = \mathbf{a}_{\rm{rx},y}^{(i)}(\bm{\Omega}) \otimes \mathbf{a}_{\rm{rx},x}^{(i)}(\bm{\Omega})}
$$

此修正后的形式与 MATLAB 代码 `kron(a_rx_y, a_rx_x)` 完全一致。发射端同理。

### :warning: 11.2 粗体 $\bm{\theta}$ 与标量 $\theta$ 的歧义

论文使用 $\bm{\theta}_{n,k} = [\varphi_{t,n,k}, \theta_{t,n,k}]^T$ 表示 **AoD 角度对向量**，同时用 $\theta$ 表示**俯仰角标量**。在同一段落中两者混用容易混淆。

**建议**：阅读时区分——粗体 $\bm{\theta}$ 为 2D 向量，常规体 $\theta$ 为标量俯仰角。后续版本可考虑用更明确符号（如 $\bm{\Theta}$ 或 $\bm{\psi}$）表示 AoD 向量。

### :warning: 11.3 式(7)中下标笔误

**原文**式(7)中：
$$
\mathbf{a}_{\rm{tx}}^{H}(\bm{\theta}_{r,n,k})
$$

下标 $r$ 不当前往出现在发射角（AoD）的参数中。$\bm{\theta}_{r,n,k}$ 应更正为 $\bm{\theta}_{n,k}$（AoD 的 $r$ 下标为笔误）。

### :warning: 11.4 漫反射衰减指数约定

**原文**：$\Gamma = \left(\frac{1+\cos\beta_{n,k}}{2}\right)^{\frac{\alpha_R}{2}}$，其中 $\alpha_R$ 未指定默认值。

**MATLAB 代码**：`Gamma = ((1 + dot_product) / 2)^alpha_rough`，其中 `alpha_rough = 2`。

两者的关系为 $\alpha_R = 2 \times \text{alpha\_rough}$。本文档遵从论文约定（指数为 $\alpha_R/2$），即论文 $\alpha_R = 4$ 等价于代码 `alpha_rough = 2`。

### :warning: 11.5 多子载波目标函数未显式给出

论文推导以单子载波为对象，最终目标函数 $J^{(i)}$ 仅含单子载波的协方差矩阵 $\mathbf{R}^{(i)}$。实际 OFDM 系统有 $I = 64$ 个子载波，代码已实现了 $I$ 个子载波的算术平均（见 [§5.4](#54-多子载波扩展)）。论文后续版本应显式加入此扩展。

---

## 附录 A：代码文件映射

| 文件 | 功能 |
|------|------|
| `main.m` | 主仿真脚本：参数初始化、信道生成、SA2N/Grid2N 调用、坐标转换、误差计算、3D 可视化 |
| `SA2N_3D_AOA.m` | SA2N 算法实现（含 `eval_J` 和 `eval_grad_hess` 辅助函数） |
| `Grid2N_3D_AOA.m` | Grid2N 算法实现（含 `eval_J` 和 `eval_grad_hess` 辅助函数） |
| `Plot_Spatial_Spectrum.m` | 高分辨率空间谱 2D 伪彩图（$2^\circ$ 步长，$181 \times 91$ 网格） |

## 附录 B：默认仿真参数

```
fc          = 28e9          Hz
c           = 3e8           m/s
delta_f     = 120e3         Hz
I           = 64            子载波数
N_tx = N_ty = 8             BS 阵元数
N_rx = N_ry = 8             UAV 阵元数
N_t = N_r   = 64            总阵元数
dx = dy     = lambda_c / 2  阵元间距
SNR_dB      = 10            dB
sigma_s2    = 1             发射信号功率
alpha_R     = 2             粗糙度指数 (论文约定, 指数为 α_R/2)
M           = 50            快拍数
p_b         = [0; -10; 10]  仿真 BS 坐标 (仅用于生成 ground truth)
p_k         = [0; 10; 8]    仿真 UAV 坐标 (仅用于生成 ground truth)
rsp_n       = [0; 0; 0]     仿真反射点坐标 (仅用于生成 ground truth)
n           = [0; 0; 1]     仿真反射面法向量 (仅用于生成 ground truth)
```

> :information_source: 所有预设坐标仅用于仿真中生成信道和计算 ground truth 对比误差，**算法本身不接受任何几何参数作为输入**。

---

*本文档对应 MATLAB 代码版本：`develop-spatial-sampling` 分支，commit `258418e`。*
*论文："Robust Positioning for mmWave Beam-Scanning in Diffuse Channels via Hybrid Optimization" (IEEE 会议)。*
