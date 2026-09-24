# 基于互功率谱加权最小二乘的 TDOA 盲提取算法

> 算法参考文档 — 整合盲几何重建研究场景，推导从 AoA 估计后的标量信号中盲提取跨 UAV 到达时间差 (TDOA) 的完整算法。
>
> 本文档与 [3D_AoA_Estimation_Algorithm.md](3D_AoA_Estimation_Algorithm.md) 及 [Reflection_Parameter_Estimation.md](Reflection_Parameter_Estimation.md) 协同，构成盲几何重建链条中**第一层 1b**（信号 → TDOA/DDOA）的算法基础。
>
> **符号体系以 [3D_AoA_Estimation_Algorithm.md](3D_AoA_Estimation_Algorithm.md) §2 符号表为准，与 Reflection_Parameter_Estimation.md 保持一致。**

---

## 目录

1. [问题定位与研究动机](#1-问题定位与研究动机)
2. [信号模型与空间滤波](#2-信号模型与空间滤波)
3. [跨 UAV 互功率谱构建](#3-跨-uav-互功率谱构建)
4. [加权最小二乘 TDOA 估计](#4-加权最小二乘-tdoa-估计)
5. [空间几何约束生成](#5-空间几何约束生成)
6. [与现有算法的集成接口](#6-与现有算法的集成接口)
7. [数值考虑与实现细节](#7-数值考虑与实现细节)

---

## 1. 问题定位与研究动机

### 1.1 在盲几何重建中的位置

研究总目标：从 $K$ 个 UAV 接收到的漫反射 OFDM 信号中，**不依赖任何先验位置信息**地重建全部空间几何。

```
第一阶段 [信号 → 角度 + 时延 + 能量]
  ├── 1a. AoA 估计  ← SA2N / Grid2N ✅
  │     文档: 3D_AoA_Estimation_Algorithm.md
  │
  ├── 1b. TDOA 估计 ← 本文档 ⏸️
  │     AoA 引导波束成形 → 标量信号 → 互功率谱 → WLS → Δτ̂, Δd̂
  │
  └── 1c. 反射参数  ← VARPRO + 消零投影 ✅
        文档: Reflection_Parameter_Estimation.md
```

**仅靠 AoA 的局限**：多个 UAV 的 AoA 射线交汇可确定反射点**方向**，但缺乏**距离尺度**——不知道沿射线走多远才能到达反射点。TDOA 提供了这个缺失的距离约束。

**TDOA 的物理来源**：同一波束经反射面散射后到达不同 UAV 的路径长度不同（$\tau_{n,k}$ 的差异）。此差异以子载波间线性相位斜率的形式编码在接收信号中。

### 1.2 核心挑战：非合作发射源

BS 发射符号 $s_{n,i,m}$ 是未知复高斯/QAM 随机信号。其随机相位 $\angle s_{n,i,m}$ 会彻底淹没传播时延的相位信息。因此：

- **单架 UAV 无法从绝对相位提取 ToF**（不可观测性——未知符号相位与传播时延耦合）
- **多 UAV 的互功率谱通过共轭相乘消除 $s$ 的随机相位**，仅保留时延差

---

## 2. 信号模型与空间滤波

### 2.1 原始接收信号模型

沿用 [3D_AoA_Estimation_Algorithm.md](3D_AoA_Estimation_Algorithm.md) §4 的信号模型。对第 $n$ 波束、第 $k$ 个 UAV、第 $i$ 子载波、第 $m$ 快拍：

$$
\mathbf{r}_{n,k,i,m} = \mathbf{H}_{n,k,i} \, \mathbf{a}_{\rm{tx}}^{(i)}(\bm{\theta}_{n,k}) \, s_{n,i,m} + \bm{\omega}_{n,k,i,m}
$$

代入信道矩阵（同 AoA 文档 §4.3 式）：

$$
\mathbf{H}_{n,k,i} = \Gamma_{n,k} \cdot e^{-j 2\pi f_i \tau_{n,k}} \cdot \mathbf{a}_{\rm{rx}}^{(i)}(\bm{\Omega}_{n,k}) \cdot \left[\mathbf{a}_{\rm{tx}}^{(i)}(\bm{\theta}_{n,k})\right]^H
$$

其中：

| 符号 | 含义 | 定义位置 |
|------|------|----------|
| $\Gamma_{n,k} = \bigl(\frac{1+\cos\beta_{n,k}}{2}\bigr)^{\frac{\alpha_R}{2}}$ | Phong 漫反射振幅因子 | AoA 文档 §3.3 |
| $\tau_{n,k} = (\|\mathbf{v}_{n,\text{in}}\| + \|\mathbf{v}_{n,k,\text{out}}\|)/c$ | 传播时延 | AoA 文档 §3.1 |
| $\bm{\Omega}_{n,k} = [\varphi_{r,n,k}, \theta_{r,n,k}]^T$ | AoA | AoA 文档 §2 |
| $\bm{\theta}_{n,k} = [\varphi_{t,n,k}, \theta_{t,n,k}]^T$ | AoD | AoA 文档 §2 |

利用 $\left[\mathbf{a}_{\rm{tx}}^{(i)}\right]^H \mathbf{a}_{\rm{tx}}^{(i)} = N_t$（$N_t = N_{tx} \times N_{ty}$），信号模型简化为：

$$
\boxed{\mathbf{r}_{n,k,i,m} = N_t \Gamma_{n,k} \cdot e^{-j 2\pi f_i \tau_{n,k}} \cdot \mathbf{a}_{\rm{rx}}^{(i)}(\bm{\Omega}_{n,k}) \cdot s_{n,i,m} + \bm{\omega}_{n,k,i,m}}
$$

### 2.2 AoA 引导的空间滤波

SA2N / Grid2N 给出 $\hat{\bm{\Omega}}_{n,k}$ 后，进行接收波束成形（与 Reflection_Parameter_Estimation.md §2.1 一致）：

$$
\boxed{y_{n,k,i,m} = \left[\mathbf{a}_{\rm{rx}}^{(i)}(\hat{\bm{\Omega}}_{n,k})\right]^H \mathbf{r}_{n,k,i,m}}
$$

展开：

$$
\begin{aligned}
y_{n,k,i,m} &= N_t \Gamma_{n,k} \cdot e^{-j 2\pi f_i \tau_{n,k}} \cdot \underbrace{\left[\mathbf{a}_{\rm{rx}}^{(i)}(\hat{\bm{\Omega}}_{n,k})\right]^H \mathbf{a}_{\rm{rx}}^{(i)}(\bm{\Omega}_{n,k})}_{G_{n,k}^{(i)}\;\text{(波束成形阵列增益)}} \cdot \, s_{n,i,m} + \tilde{n}_{n,k,i,m}
\end{aligned}
$$

其中 $\tilde{n}_{n,k,i,m}$ 为滤波后等效噪声，方差为 $N_r \sigma_n^2$（同 Reflection_Parameter_Estimation.md §2.1）。

当 $\hat{\bm{\Omega}}_{n,k} \approx \bm{\Omega}_{n,k}$ 时，$G_{n,k}^{(i)} \approx N_r$（$N_r = N_{rx} \times N_{ry}$）。与 Reflection_Parameter_Estimation.md 一致，定义**波束成形复合幅度**：

$$
\boxed{\tilde{\alpha}_{n,k} \triangleq N_t N_r \Gamma_{n,k}}
$$

标量信号紧凑表示为：

$$
\boxed{y_{n,k,i,m} = \tilde{\alpha}_{n,k} \cdot e^{-j 2\pi f_i \tau_{n,k}} \cdot s_{n,i,m} + \tilde{n}_{n,k,i,m}}
$$

---

## 3. 跨 UAV 互功率谱构建

### 3.1 共轭相乘消除随机符号相位

选定 UAV 1 为参考节点，UAV $k$ 为目标（$k = 2,\dots,K$）。对同一子载波 $i$、同一快拍 $m$，构建互功率谱：

$$
R_{n,k,1}^{(m)}[i] = y_{n,k,i,m} \cdot y_{n,1,i,m}^*
$$

展开：

$$
\begin{aligned}
R_{n,k,1}^{(m)}[i] &= \left( \tilde{\alpha}_{n,k} \, s_{n,i,m} \, e^{-j 2\pi f_i \tau_{n,k}} + \tilde{n}_{k} \right) \cdot \left( \tilde{\alpha}_{n,1}^* \, s_{n,i,m}^* \, e^{+j 2\pi f_i \tau_{n,1}} + \tilde{n}_{1}^* \right) \\[4pt]
&= \underbrace{\tilde{\alpha}_{n,k} \tilde{\alpha}_{n,1}^* \cdot |s_{n,i,m}|^2 \cdot e^{-j 2\pi f_i (\tau_{n,k} - \tau_{n,1})}}_{\text{期望信号项 } S_{n,k,1}^{(m)}[i]} \;+\; \underbrace{\text{交叉噪声项 } V_{n,k,1}^{(m)}[i]}_{\text{含 } s \cdot \tilde{n}^*,\; s^* \cdot \tilde{n},\; \tilde{n} \cdot \tilde{n}^*}
\end{aligned}
$$

**关键代数坍缩**：

$$
\boxed{s_{n,i,m} \cdot s_{n,i,m}^* = |s_{n,i,m}|^2 \in \mathbb{R}^+}
$$

复数符号 $s$ 的随机相位被**精确消除**。$|s|^2$ 坍缩为纯正实数，自然成为信号强度权重。

**跨快拍平均**（$M$ 次独立快拍）：

$$
\boxed{R_{n,k,1}[i] = \frac{1}{M} \sum_{m=1}^{M} R_{n,k,1}^{(m)}[i]}
$$

交叉噪声项 $V$ 在 $M$ 次平均后有效抑制（$M = 50$ 提供约 $17$ dB 噪声抑制增益）。

### 3.2 相位提取：从复数到线性关系

忽略已被平均抑制的噪声：

$$
R_{n,k,1}[i] \approx |\tilde{\alpha}_{n,k}| |\tilde{\alpha}_{n,1}| \cdot \bar{P}_{n,i} \cdot e^{j(\phi_{\text{offset},k} - \phi_{\text{offset},1})} \cdot e^{-j 2\pi f_i (\tau_{n,k} - \tau_{n,1})}
$$

其中 $\bar{P}_{n,i} = \frac{1}{M} \sum_m |s_{n,i,m}|^2 \in \mathbb{R}^+$ 为第 $i$ 子载波的平均符号功率。定义相位：

$$
\boxed{\Phi_{n,k,1}[i] = \angle R_{n,k,1}[i]}
$$

$\angle(\cdot) = \operatorname{atan2}(\Im\{\cdot\}, \Re\{\cdot\})$，值域 $(-\pi, \pi]$。

将 $f_i = f_c + i \cdot \Delta f$ 代入展开：

$$
\begin{aligned}
\Phi_{n,k,1}[i] &= \underbrace{(\phi_{\text{offset},k} - \phi_{\text{offset},1})}_{\text{① 射频初相差}} \;-\; \underbrace{2\pi f_c (\tau_{n,k} - \tau_{n,1})}_{\text{② 载波相位}} \;-\; \underbrace{2\pi i \Delta f (\tau_{n,k} - \tau_{n,1})}_{\text{③ 子载波相位（线性项）}} \\[6pt]
&= \beta \cdot i + b
\end{aligned}
$$

| 项 | 依赖 $i$？ | 物理来源 | WLS 中角色 |
|----|:---:|----------|-----------|
| ① $\phi_{\text{offset},k} - \phi_{\text{offset},1}$ | 否 | 射频本振初相差 + 反射路径固定相差 | 并入截距 $b$ |
| ② $-2\pi f_c \Delta\tau$ | 否 | 载波在时延差上的相位旋转 | 并入截距 $b$ |
| ③ $-2\pi i \Delta f \Delta\tau$ | **是，线性** | 子载波编号每增 1，额外积累的相位 | **斜率 $\beta$** |

**线性关系总结**：

$$
\boxed{\Phi_{n,k,1}[i] = \beta \cdot i + b, \qquad \beta = -2\pi \Delta f \cdot \Delta\tau_{n,k,1}}
$$

其中 $\Delta\tau_{n,k,1} \triangleq \tau_{n,k} - \tau_{n,1}$。

**随机符号相位消失的逐项追踪**：

```
y_{n,k,i,m}:  ∠s + ϕ_offset,k − 2πf_i τ_k
y_{n,1,i,m}*: −∠s − ϕ_offset,1 + 2πf_i τ1

共轭相乘后相位求和:
  ∠s − ∠s = 0  ← 精确抵消!

剩余:
  (ϕ_offset,k − ϕ_offset,1) − 2πf_i(τ_k − τ₁)
  = Δϕ − 2πf_i · Δτ
```

**不需要解调 $s$、不需要知道调制格式、不需要导频**——只要两个 UAV 收到同一个 $s$，共轭相乘即可消去随机相位。

### 3.3 相位解缠绕

$\angle(\cdot)$ 将相位折叠到 $(-\pi, \pi]$。在大时延差下，实际相位可能超出此范围，需要解缠绕。

**解缠绕条件**：相邻子载波相位增量 $|\beta| = 2\pi \Delta f |\Delta\tau| < \pi$，即：

$$
|\Delta\tau| < \frac{1}{2\Delta f} \approx 4.17\;\mu\text{s} \quad\Longleftrightarrow\quad |\Delta d| < 1250\;\text{m}
$$

典型 UAV 编队（间距 8–15 m，$\Delta\tau \approx 27-50$ ns）远小于此阈值。使用 `unwrap(Φ)` 沿 $i$ 方向做一维解缠绕，恢复连续下降的直线。

---

## 4. 加权最小二乘 TDOA 估计

### 4.1 为何必须加权

复高斯信号 $s \sim \mathcal{CN}(0, \sigma_s^2)$ 的能量 $|s|^2$ 服从指数分布：

- 约 37% 子载波能量低于平均值（深度衰落）
- 深衰落子载波相位几乎由噪声主导，不可靠

**加权策略**：以互功率谱幅值为权重，物理含义为"信号越强 → 互功率谱越亮 → 相位越可信"：

$$
\boxed{w_{n,k,1}[i] = |R_{n,k,1}[i]| \;\propto\; |\tilde{\alpha}_{n,k}\tilde{\alpha}_{n,1}| \cdot |s_{n,i}|^2}
$$

### 4.2 WLS 目标函数与闭式解

线性模型 $\Phi[i] = \beta \cdot i + b$（以下略去下标 $n,k,1$ 便于阅读），最小化加权残差平方和：

$$
\boxed{J(\beta, b) = \sum_{i=0}^{I-1} w_i \left( \Phi_i - \beta \cdot i - b \right)^2}
$$

**步骤 1**：对 $b$ 求偏导置零。

$$
\frac{\partial J}{\partial b} = -2 \sum_{i=0}^{I-1} w_i \left( \Phi_i - \beta \cdot i - b \right) = 0
$$

定义加权平均：$W = \sum_i w_i$，$\bar{\Phi}_w = \frac{1}{W} \sum_i w_i \Phi_i$，$\bar{i}_w = \frac{1}{W} \sum_i w_i i$。

$$
\boxed{b = \bar{\Phi}_w - \beta \, \bar{i}_w} \tag{A}
$$

**步骤 2**：对 $\beta$ 求偏导置零。

$$
\frac{\partial J}{\partial \beta} = -2 \sum_{i=0}^{I-1} w_i \cdot i \cdot \left( \Phi_i - \beta \cdot i - b \right) = 0
$$

代入 (A) 消去 $b$：

$$
\sum_{i=0}^{I-1} w_i \cdot i \cdot (\Phi_i - \bar{\Phi}_w) = \beta \sum_{i=0}^{I-1} w_i \cdot i \cdot (i - \bar{i}_w)
$$

**步骤 3**：解得最优斜率。

$$
\boxed{\hat{\beta} = \frac{\sum_{i=0}^{I-1} w_i (i - \bar{i}_w)(\Phi_i - \bar{\Phi}_w)}{\sum_{i=0}^{I-1} w_i (i - \bar{i}_w)^2}}
$$

**步骤 4**：反解 TDOA 和 DDOA。

$$
\boxed{\begin{aligned}
\Delta\hat{\tau}_{n,k,1} &= -\frac{\hat{\beta}}{2\pi \Delta f} \\[6pt]
\Delta\hat{d}_{n,k,1} &= c \cdot \Delta\hat{\tau}_{n,k,1}
\end{aligned}}
$$

**精度来源**：$I = 64$ 子载波提供足够频域采样；波束成形提供约 $18$ dB 阵列增益（$N_r = 64$）；$M = 50$ 快拍平均提供约 $17$ dB 噪声抑制。联合等效 SNR 远高于原始接收 SNR。

---

## 5. 空间几何约束生成

$N$ 个波束 × $(K-1)$ 个 UAV 对 = $N(K-1)$ 个独立 DDOA 测量值。每对 $(k,1)$ 的同一波束 $n$ 产生双曲面约束：

$$
\|\mathbf{rsp}_n - \mathbf{p}_k\| - \|\mathbf{rsp}_n - \mathbf{p}_1\| = \Delta\hat{d}_{n,k,1}
$$

在第二阶段联合求解中，DDOA 与 AoA 方向约束互补：

| 约束类型 | 数量 | 提供 |
|----------|------|------|
| AoA 方向（Phase 1a） | $NK$ | 2D 射线方向 |
| DDOA 距离差（Phase 1b） | $N(K-1)$ | 1D 距离差（双曲面） |
| 镜面方向（Phase 1c） | $N$ | 反射面出射方向 |
| **联合** | — | 3D 位置唯一确定 |

---

## 6. 与现有算法的集成接口

### 6.1 端到端处理流程（单波束 $n$）

```
1. AoA 估计 (SA2N / Grid2N)                  ← 已有
   输入: R_{n,k}^{(i)}     输出: Ω̂_{n,k}

2. 空间滤波                                    ← 新增
   y_{n,k,i,m} = a_rx^H(Ω̂_{n,k}, λ_i) · r_{n,k,i,m}

3. 互功率谱 (UAV k × UAV 1*)                  ← 新增
   R_{n,k,1}[i] = (1/M) Σ_m y_{n,k,i,m} · y*_{n,1,i,m}

4. 相位提取 + 解缠绕                           ← 新增
   Φ_{n,k,1}[i] = unwrap(∠ R_{n,k,1}[i])

5. WLS 线性拟合                                 ← 新增
   w_i = |R_{n,k,1}[i]|
   β̂ = Σ w_i(i-ī_w)(Φ_i-Φ̄_w) / Σ w_i(i-ī_w)²

6. TDOA/DDOA 输出                               ← 新增
   Δτ̂ = -β̂/(2πΔf),   Δd̂ = c·Δτ̂
```

### 6.2 计算复杂度

| 步骤 | 复杂度 | 备注 |
|------|--------|------|
| AoA 估计 | $O(NK \cdot I \cdot N_r^2)$ | 主开销，已有实现 |
| 空间滤波 | $O(NK \cdot I \cdot M \cdot N_r)$ | 新增 |
| 互功率谱 + WLS | $O(NK \cdot I \cdot M)$ | 新增，可忽略 |
| TDOA 总额外开销 | — | 远小于 AoA 估计阶段 |

### 6.3 输入输出契约

| 方向 | 内容 | 来源/去向 |
|------|------|-----------|
| **输入** | 原始接收向量 $\mathbf{r}_{n,k,i,m}$ | 接收前端 |
| **输入** | AoA 估计 $\hat{\bm{\Omega}}_{n,k}$ | SA2N / Grid2N (1a) |
| **输出** | TDOA $\Delta\hat{\tau}_{n,k,1}$ | → 第二阶段 DDOA 约束 |
| **输出** | DDOA $\Delta\hat{d}_{n,k,1}$ | → 几何反演 |

---

## 7. 数值考虑与实现细节

### 7.1 相位解缠绕

`unwrap(Φ)` 沿 $i$ 方向做一维解缠绕。缠绕条件 $|\Delta\tau| < 1/(2\Delta f) \approx 4.17\;\mu\text{s}$（距离差 $< 1250$ m）对典型 UAV 编队总是满足。

### 7.2 深衰落子载波

当 $|R[i]|$ 极低时相位为纯噪声。WLS 权重 $w_i = |R[i]|$ 自动降低其影响。可选择性删除 $w_i < 0.1 \times \max(w_i)$ 的子载波，确保剩余 $I' \ge 10$。

### 7.3 多波束一致性

同一 UAV 对 $(k,1)$ 上，$N$ 个波束的 $\Delta\hat{\tau}_{n,k,1}$ 应对不同 $n$ 近似相同（UAV 位置不变）。利用此性质做离群值检测：若某波束偏离显著，可能 AoA 估计有误或遭遇深度衰落。

### 7.4 参考 UAV 选择

当前采用 UAV 1 固定参考。若 UAV 1 处于深度衰落，所有测量同时降质。改进方案（待后续实现）：采用成对比较（all-pairs）或质心参考，提高稳健性。

---

## 附录：符号速查

| 符号 | 含义 | 定义位置 |
|------|------|----------|
| $n$ | 波束编号 $1,\dots,N$ | AoA §2 |
| $k$ | UAV 编号 $1,\dots,K$ | AoA §2 |
| $i$ | 子载波编号 $0,\dots,I-1$ | AoA §4 |
| $m$ | 快拍编号 $1,\dots,M$ | AoA §4 |
| $\bm{\Omega}_{n,k}$ | AoA $[\varphi_{r,n,k}, \theta_{r,n,k}]^T$ | AoA §2 |
| $\mathbf{a}_{\rm{rx}}^{(i)}(\bm{\Omega})$ | 接收导向矢量 | AoA §4.2 |
| $\mathbf{a}_{\rm{tx}}^{(i)}(\bm{\theta})$ | 发射导向矢量 | AoA §4.2 |
| $\Gamma_{n,k}$ | Phong 振幅因子 $(\frac{1+\cos\beta_{n,k}}{2})^{\alpha_R/2}$ | AoA §3.3 |
| $\tau_{n,k}$ | 传播时延 | AoA §3.1 |
| $\tilde{\alpha}_{n,k}$ | 波束成形复合幅度 $N_t N_r \Gamma_{n,k}$ | Reflection §2.1 |
| $\sigma_n^2$ | 噪声功率 | AoA §5.2 |
| $\sigma_s^2$ | 信号功率 | AoA §4 |
| $\Delta f$ | 子载波间隔 $120$ kHz | AoA §4 |
| $f_c$ | 载波频率 $28$ GHz | AoA §4 |

---

*本文档与 [3D_AoA_Estimation_Algorithm.md](3D_AoA_Estimation_Algorithm.md) 及 [Reflection_Parameter_Estimation.md](Reflection_Parameter_Estimation.md) 共同构成盲几何重建第一阶段（信号 → 角度 + 时延 + 能量）的完整算法体系。*
