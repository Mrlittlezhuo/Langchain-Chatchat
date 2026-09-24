# 基于互功率谱加权最小二乘的 TDOA 盲提取算法

> 算法参考文档 — 整合盲几何重建研究场景，推导从 AoA 估计后的标量信号中盲提取跨 UAV 到达时间差 (TDOA) 的完整算法。
>
> 本文档与 [3D_AoA_Estimation_Algorithm.md](3D_AoA_Estimation_Algorithm.md) 及 [Reflection_Parameter_Estimation.md](Reflection_Parameter_Estimation.md) 协同，构成盲重建链条中**第一层 1b**（信号 → TDOA）的算法基础。
>
> **符号体系以 [3D_AoA_Estimation_Algorithm.md](3D_AoA_Estimation_Algorithm.md) §2 符号表为准，与 Reflection_Parameter_Estimation.md 保持一致。**

---

## 目录

1. [问题定位与研究动机](#1-问题定位与研究动机)
2. [信号模型回顾与空间滤波](#2-信号模型回顾与空间滤波)
   - 2.1 [原始接收信号模型](#21-原始接收信号模型)
   - 2.2 [AoA 引导的空间滤波](#22-aoa-引导的空间滤波)
   - 2.3 [多快拍融合](#23-多快拍融合)
3. [跨 UAV 互功率谱构建](#3-跨-uav-互功率谱构建)
   - 3.1 [共轭相乘消除随机符号相位](#31-共轭相乘消除随机符号相位)
   - 3.2 [相位提取：从复数到线性关系](#32-相位提取从复数到线性关系)
   - 3.3 [相位提取的数值实例](#33-相位提取的数值实例)
4. [加权最小二乘 TDOA 估计](#4-加权最小二乘-tdoa-估计)
   - 4.1 [为何必须加权](#41-为何必须加权)
   - 4.2 [WLS 目标函数](#42-wls-目标函数)
   - 4.3 [闭式解推导](#43-闭式解推导)
5. [多波束与多 UAV 联合处理](#5-多波束与多-uav-联合处理)
6. [空间几何约束生成](#6-空间几何约束生成)
7. [与 SA2N/Grid2N 的集成](#7-与-sa2ngrid2n-的集成)
8. [数值考虑与实现细节](#8-数值考虑与实现细节)

---

## 1. 问题定位与研究动机

### 1.1 在盲几何重建中的位置

研究总目标：从 $K$ 个 UAV 接收到的漫反射 OFDM 信号中，**不依赖任何先验位置信息**地重建全部空间几何。

```
第一层 [信号 → 角度 + 时延]
  ├── 1a. AoA 估计 ← SA2N / Grid2N (已有)
  │     接收信号 → 协方差矩阵 → J(Ω) 最大化 → (φ̂, θ̂)
  │
  └── 1b. TDOA 估计 ← 本文档 (新增)
        AoA 引导波束成形 → 标量信号 → 互功率谱 → WLS → Δτ̂
```

**仅靠 AoA 的局限**：多个 UAV 的 AoA 射线交汇可确定反射点方向，但缺乏距离尺度——不知道沿射线走多远。TDOA 提供了这个缺失的距离约束。

**TDOA 的物理来源**：同一波束经反射面散射后到达不同 UAV 的路径长度不同，产生时间差。此差异以子载波间线性相位斜率的形式编码在接收信号中。

### 1.2 核心挑战：非合作发射源

BS 发射符号 $s_{n,i,m}$ 是未知复高斯/QAM 随机信号。其随机相位 $\angle s_{n,i,m}$ 会彻底淹没传播时延的相位信息。因此：

- **单架 UAV 无法从绝对相位提取 ToF**（不可观测性）
- **多 UAV 的互功率谱通过共轭相乘消除 $s$ 的随机相位**，仅保留时延差

---

## 2. 信号模型回顾与空间滤波

### 2.1 原始接收信号模型

对第 $n$ 波束、第 $k$ 个 UAV、第 $i$ 子载波、第 $m$ 快拍：

$$
\mathbf{r}_{n,k,i,m} = \mathbf{H}_{n,k,i} \, \mathbf{a}_{\rm{tx}}^{(i)}(\bm{\theta}_{n,k}) \, s_{n,i,m} + \bm{\omega}_{n,k,i,m}
$$

代入信道矩阵 $\mathbf{H}_{n,k,i}$：

$$
\mathbf{H}_{n,k,i} = \Gamma_{n,k} \cdot e^{-j 2\pi f_i \tau_{n,k}} \cdot \mathbf{a}_{\rm{rx}}^{(i)}(\bm{\Omega}_{n,k}) \cdot \left[\mathbf{a}_{\rm{tx}}^{(i)}(\bm{\theta}_{n,k})\right]^H
$$

其中 $\Gamma_{n,k} = \left(\frac{1+\cos\beta_{n,k}}{2}\right)^{\frac{\alpha_R}{2}}$ 为 Phong 漫反射振幅因子（同 AoA 文档 §3.3）。利用 $\left[\mathbf{a}_{\rm{tx}}^{(i)}\right]^H \mathbf{a}_{\rm{tx}}^{(i)} = N_t$（$N_t = N_{tx} \times N_{ty}$，同 AoA 文档 §2）：

$$
\boxed{\mathbf{r}_{n,k,i,m} = N_t \Gamma_{n,k} \cdot e^{-j 2\pi f_i \tau_{n,k}} \cdot \mathbf{a}_{\rm{rx}}^{(i)}(\bm{\Omega}_{n,k}) \cdot s_{n,i,m} + \bm{\omega}_{n,k,i,m}}
$$

### 2.2 AoA 引导的空间滤波

SA2N / Grid2N 给出 $\hat{\bm{\Omega}}_{n,k}$ 后，接收波束成形将 $N_r \times 1$ 向量压缩为标量：

$$
\boxed{y_{n,k,i,m} = \left[\mathbf{a}_{\rm{rx}}^{(i)}(\hat{\bm{\Omega}}_{n,k})\right]^H \mathbf{r}_{n,k,i,m}}
$$

展开：

$$
\begin{aligned}
y_{n,k,i,m} &= N_t \Gamma_{n,k} \cdot e^{-j 2\pi f_i \tau_{n,k}} \cdot \underbrace{\left[\mathbf{a}_{\rm{rx}}^{(i)}(\hat{\bm{\Omega}}_{n,k})\right]^H \mathbf{a}_{\rm{rx}}^{(i)}(\bm{\Omega}_{n,k})}_{G_{n,k}^{(i)}\;\text{(阵列增益)}} \cdot \, s_{n,i,m} + \tilde{n}_{n,k,i,m}
\end{aligned}
$$

其中 $\tilde{n}_{n,k,i,m}$ 为等效噪声，方差为 $N_r \sigma_n^2$（同 Reflection_Parameter_Estimation.md §2.1）。定义波束成形复合幅度（与 Reflection_Parameter_Estimation.md 一致）：

$$
\boxed{\tilde{\alpha}_{n,k} \triangleq N_t N_r \Gamma_{n,k}}
$$

标量信号紧凑表示为：

$$
\boxed{y_{n,k,i,m} = \tilde{\alpha}_{n,k} \cdot e^{-j 2\pi f_i \tau_{n,k}} \cdot s_{n,i,m} + \tilde{n}_{n,k,i,m}}
$$

### 2.3 多快拍融合

我们有 $M = 50$ 个快拍。对 TDOA 估计，最有效的方式是直接构建快拍平均后的互功率谱。

---

## 3. 跨 UAV 互功率谱构建

### 3.1 共轭相乘消除随机符号相位

选定 UAV 1 为参考节点，UAV $k$ 为目标。对同一子载波 $i$、同一快拍 $m$：

$$
R_{n,k,1}^{(m)}[i] = y_{n,k,i,m} \cdot y_{n,1,i,m}^*
$$

展开：

$$
\begin{aligned}
R_{n,k,1}^{(m)}[i] &= \left( \tilde{\alpha}_{n,k} s e^{-j 2\pi f_i \tau_{n,k}} + \tilde{n}_k \right) \cdot \left( \tilde{\alpha}_{n,1}^* s^* e^{+j 2\pi f_i \tau_{n,1}} + \tilde{n}_1^* \right) \\[4pt]
&= \underbrace{\tilde{\alpha}_{n,k} \tilde{\alpha}_{n,1}^* \cdot |s_{n,i,m}|^2 \cdot e^{-j 2\pi f_i (\tau_{n,k} - \tau_{n,1})}}_{\text{期望信号项 } S_{n,k,1}^{(m)}[i]} \;+\; \underbrace{\text{交叉噪声项 } V_{n,k,1}^{(m)}[i]}_{\text{含 } s \cdot n^*,\; s^* \cdot n,\; n \cdot n^*}
\end{aligned}
$$

**关键代数坍缩**：

$$
\boxed{s_{n,i,m} \cdot s_{n,i,m}^* = |s_{n,i,m}|^2 \in \mathbb{R}^+}
$$

复数符号 $s$ 的随机相位被**完全消除**。$|s|^2$ 坍缩为纯正实数，自然成为信号强度权重。

**跨快拍平均**：

$$
\boxed{R_{n,k,1}[i] = \frac{1}{M} \sum_{m=1}^{M} R_{n,k,1}^{(m)}[i] = \frac{1}{M} \sum_{m=1}^{M} y_{n,k,i,m} \cdot y_{n,1,i,m}^*}
$$

交叉噪声项 $V$ 在 $M$ 次平均后有效抑制。$M = 50$ 提供约 $17$ dB 噪声抑制增益。

### 3.2 相位提取：从复数到线性关系

**3.2.1 互功率谱的极坐标表示**

忽略已被平均抑制的噪声，将 $\tilde{\alpha}_{n,k} = |\tilde{\alpha}_{n,k}| e^{j\phi_{\text{offset},k}}$ 代入：

$$
\begin{aligned}
R_{n,k,1}[i] &\approx |\tilde{\alpha}_{n,k}| |\tilde{\alpha}_{n,1}| \cdot \bar{P}_{n,i} \cdot e^{j(\phi_{\text{offset},k} - \phi_{\text{offset},1})} \cdot e^{-j 2\pi f_i (\tau_{n,k} - \tau_{n,1})} \\[6pt]
&= A_i \cdot e^{\,j(\Delta\phi_{n,k,1} - 2\pi f_i \Delta\tau_{n,k,1})}
\end{aligned}
$$

其中 $\bar{P}_{n,i} = \frac{1}{M} \sum_m |s_{n,i,m}|^2 \in \mathbb{R}^+$ 为平均功率，$A_i$ 为正实数幅值。

**3.2.2 相位提取**

$\angle(\cdot) = \operatorname{atan2}(\Im\{\cdot\}, \Re\{\cdot\})$，值域 $(-\pi, \pi]$：

$$
\boxed{\Phi_{n,k,1}[i] = \angle R_{n,k,1}[i] = \Delta\phi_{n,k,1} - 2\pi f_i \cdot \Delta\tau_{n,k,1}}
$$

**3.2.3 逐项拆解：物理来源**

将 $f_i = f_c + i \cdot \Delta f$ 代入：

$$
\Phi[i] = \underbrace{\Delta\phi_{n,k,1}}_{\text{① 固定相差}} \;-\; \underbrace{2\pi f_c \Delta\tau_{n,k,1}}_{\text{② 载波相位}} \;-\; \underbrace{2\pi i \Delta f \Delta\tau_{n,k,1}}_{\text{③ 子载波相位（线性）}}
$$

| 项 | 依赖 $i$？ | 物理来源 | WLS 中角色 |
|----|:---:|----------|-----------|
| ① $\Delta\phi = \phi_{\text{offset},k} - \phi_{\text{offset},1}$ | 否 | 射频本振初相差 + 反射路径固定相差 | 并入截距 |
| ② $-2\pi f_c \Delta\tau$ | 否 | 载波在时延差上的相位旋转 | 并入截距 |
| ③ $-2\pi i \Delta f \Delta\tau$ | **是，线性** | 子载波编号每增 1，额外积累的相位 | **斜率 $\beta$** |

**3.2.4 随机符号相位消失的详细追踪**

```
步骤 A: 波束成形后的标量信号相位
  y_k:  ∠s + φ_offset,k - 2πf_iτ_k
  y_1*: -∠s - φ_offset,1 + 2πf_iτ_1

步骤 B: 共轭相乘后的相位求和
  ∠s - ∠s = 0  ← 精确抵消！

步骤 C: 剩余项
  (φ_offset,k - φ_offset,1) - 2πf_i(τ_k - τ_1)
  = Δφ - 2πf_i·Δτ
```

**不需要解调 $s$、不需要知道调制格式、不需要导频**——只要两个 UAV 收到同一个 $s$，共轭相乘即可消去随机相位。

**3.2.5 线性关系总结**

$$
\boxed{\Phi[i] = \beta \cdot i + b, \qquad \beta = -2\pi \Delta f \cdot \Delta\tau}
$$

---

### 3.3 相位提取的数值实例

**场景**：$\Delta d \approx 20$ m，$\Delta\tau \approx 66.7$ ns，$\Delta f = 120$ kHz

| $i$ | 项 ③ $-2\pi i \Delta f \Delta\tau$ | 真实 $\Phi[i]$（设 $b=0$） |
|:---:|------|------|
| 0 | $0$ | $0$ |
| 1 | $-0.0503$ rad ($-2.9^\circ$) | $-0.0503$ |
| 10 | $-0.503$ rad ($-28.8^\circ$) | $-0.503$ |
| 63 | $-3.17$ rad ($-181.5^\circ$) | $-3.17$ |

**$\angle(\cdot)$ 实际返回值（折叠到 $(-\pi, \pi]$）**：

| $i$ | 真实 $\Phi[i]$ | $\angle(\cdot)$ 返回值 | 说明 |
|:---:|------|------|------|
| 30 | $-1.508$ | $-1.508$ | 正常 |
| 60 | $-3.016$ | $+3.267$ | **缠绕！** $-3.016 + 2\pi \approx 3.267$ |
| 63 | $-3.167$ | $+3.116$ | **缠绕！** |

**解缠绕条件**：相邻子载波相位差 $|\beta| = 2\pi \Delta f |\Delta\tau| < \pi$，即 $|\Delta\tau| < 1/(2\Delta f) \approx 4.17\;\mu\text{s}$（距离差 $< 1250$ m）。典型 UAV 编队总是满足。`unwrap()` 沿 $i$ 方向累积 $2\pi$ 修正，恢复连续下降直线。

---

## 4. 加权最小二乘 TDOA 估计

### 4.1 为何必须加权

复高斯信号 $s \sim \mathcal{CN}(0, \sigma_s^2)$ 的能量 $|s|^2$ 服从指数分布：

- 约 37% 子载波能量低于平均（深度衰落）
- 深衰落子载波相位几乎由噪声主导，不可靠

**加权策略**：以互功率谱幅值为权重：

$$
\boxed{w_{n,k,1}[i] = |R_{n,k,1}[i]| \;\propto\; |\tilde{\alpha}_{n,k}\tilde{\alpha}_{n,1}| \cdot |s_{n,i}|^2}
$$

物理直觉：信号越强 → 互功率谱越亮 → 相位越可信 → 权重越大。

### 4.2 WLS 目标函数

$$
\boxed{J(\beta, \Delta\phi) = \sum_{i=0}^{I-1} w_i \left( \Phi_i - \beta \cdot i - \Delta\phi \right)^2}
$$

（以下略去下标 $n,k,1$。）

### 4.3 闭式解推导

**步骤 1**：对 $\Delta\phi$ 求偏导置零。

$$
\frac{\partial J}{\partial \Delta\phi} = -2 \sum_{i=0}^{I-1} w_i \left( \Phi_i - \beta \cdot i - \Delta\phi \right) = 0
$$

定义加权平均：$W = \sum_i w_i$，$\bar{\Phi}_w = \frac{1}{W} \sum_i w_i \Phi_i$，$\bar{i}_w = \frac{1}{W} \sum_i w_i i$。

$$
\boxed{\Delta\phi = \bar{\Phi}_w - \beta \, \bar{i}_w} \tag{A}
$$

**步骤 2**：对 $\beta$ 求偏导置零，代入 (A)。

$$
\frac{\partial J}{\partial \beta} = -2 \sum_{i=0}^{I-1} w_i \cdot i \cdot \left( \Phi_i - \beta \cdot i - \Delta\phi \right) = 0
$$

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

**精度来源**：子载波数 $I=64$ 提供足够频域采样；波束成形提供约 18 dB 阵列增益；$M=50$ 快拍平均提供约 17 dB 噪声抑制。

---

## 5. 多波束与多 UAV 联合处理

$N$ 个波束 × $(K-1)$ 个 UAV 对 = $N(K-1)$ 个独立 TDOA 测量值。

每对 $(k,1)$ 的同一波束 $n$ 产生约束：

$$
\|\mathbf{rsp}_n - \mathbf{p}_k\| - \|\mathbf{rsp}_n - \mathbf{p}_1\| = \Delta\hat{d}_{n,k,1}
$$

与 AoA 方向约束 $\frac{\mathbf{rsp}_n - \mathbf{p}_k}{\|\mathbf{rsp}_n - \mathbf{p}_k\|} = \mathbf{u}(\hat{\varphi}_{r,n,k}, \hat{\theta}_{r,n,k})$ 联合，唯一确定相对位置。

| 约束类型 | 数量 | 提供 |
|----------|------|------|
| AoA 方向 | $NK$ | 2D 方向 |
| DDOA 距离差 | $N(K-1)$ | 1D 距离差 |
| **联合** | $3NK - N$ | 3D 位置唯一确定 |

---

## 6. 空间几何约束生成

DDOA 测量值构建三维双曲面约束：

$$
\|\mathbf{rsp}_n - \mathbf{p}_k\| - \|\mathbf{rsp}_n - \mathbf{p}_1\| = \Delta\hat{d}_{n,k,1}
$$

在盲重建链条中：

```
第一层 [信号 → 角度 + 时延]
  ├── 1a. AoA  ← SA2N / Grid2N
  └── 1b. TDOA ← 本文档

第二层 [角度 + 时延 → 反射点 + UAV 位置]
  联合 AoA 方向 + DDOA 双曲面 → rsp_n + p_k

第三层 [反射点 → 反射面 → BS]
  多反射点拟合面 → n → BS 位置
```

---

## 7. 与 SA2N/Grid2N 的集成

### 端到端处理流程（单波束 $n$）

```
1. AoA 估计 (SA2N / Grid2N)
   输入: R_{n,k}^{(i)}   输出: Ω̂_{n,k} = [φ̂, θ̂]^T

2. 空间滤波
   y_{n,k,i,m} = a_rx^H(Ω̂_{n,k}, λ_i) · r_{n,k,i,m}

3. 互功率谱 (UAV k × UAV 1*)
   R_{n,k,1}[i] = (1/M) Σ_m y_{n,k,i,m} · y*_{n,1,i,m}

4. 相位提取 + 解缠绕
   Φ_{n,k,1}[i] = unwrap(∠ R_{n,k,1}[i])

5. WLS 线性拟合
   w_i = |R_{n,k,1}[i]|
   β̂ = Σ w_i(i - ī_w)(Φ_i - Φ̄_w) / Σ w_i(i - ī_w)²

6. TDOA/DDOA 输出
   Δτ̂ = -β̂/(2πΔf),   Δd̂ = c·Δτ̂
```

| 步骤 | 复杂度 |
|------|--------|
| AoA 估计 | $O(NK \cdot I \cdot N_r^2)$ |
| 空间滤波 | $O(NK \cdot I \cdot M \cdot N_r)$ |
| 互功率谱 + WLS | $O(NK \cdot I \cdot M)$ |

主开销在 AoA 估计阶段。TDOA 部分几乎可忽略。

---

## 8. 数值考虑与实现细节

### 8.1 相位解缠绕

`unwrap(Phi)` 沿 $i$ 方向做一维解缠绕。缠绕条件 $|\Delta\tau| < 1/(2\Delta f) \approx 4.17\;\mu\text{s}$（距离差 $< 1250$ m）对典型 UAV 编队总是满足。

### 8.2 深衰落子载波

当 $|R[i]|$ 极低时相位为纯噪声。WLS 权重自动降低其影响。可选择性删除 $w_i < 0.1 \times \max(w_i)$ 的子载波，确保剩余 $I' \ge 10$。

### 8.3 多波束一致性

同一 UAV 对 $(k,1)$ 上，$N$ 个波束的 $\Delta\hat{\tau}_{n,k,1}$ 应对不同 $n$ 近似相同（UAV 位置不变）。利用此性质做离群值检测：若某波束偏离显著，可能 AoA 估计有误或遭遇深度衰落。

---

## 附录 A：符号对应

| 本文档 | AoA 文档 §2 / Reflection 文档 | 含义 |
|--------|------|------|
| $i$ | 同 | 子载波编号 $0, \dots, I-1$ |
| $I$ | 同 | 子载波数 $64$ |
| $m$ | 同 | 快拍编号 $1, \dots, M$ |
| $M$ | 同 | 快拍数 $50$ |
| $n$ | 同 | 波束编号 |
| $k$ | 同 | UAV 编号 |
| $\bm{\Omega}_{n,k}$ | AoA §2 | AoA $[\varphi_{r,n,k}, \theta_{r,n,k}]^T$ |
| $\bm{\theta}_{n,k}$ | AoA §2 | AoD $[\varphi_{t,n,k}, \theta_{t,n,k}]^T$ |
| $\Gamma_{n,k}$ | AoA §3.3 | Phong 振幅因子 $(\frac{1+\cos\beta_{n,k}}{2})^{\alpha_R/2}$ |
| $\tau_{n,k}$ | AoA §3.1 | 传播时延 |
| $\tilde{\alpha}_{n,k}$ | Reflection §2.1 | 波束成形复合幅度 $N_t N_r \Gamma_{n,k}$ |
| $\sigma_n^2$ | AoA §5.2 / Reflection §2.2 | 噪声功率 |
| $y_{n,k,i,m}$ | Reflection §2.1 | 空间滤波输出标量 |
| $\Delta\tau_{n,k,1}$ | — | TDOA |
| $\Delta\hat{d}_{n,k,1}$ | — | DDOA |

## 附录 B：默认参数

```
fc      = 28e9      Hz
Δf      = 120e3     Hz
I       = 64        子载波数
N_r     = 64        接收阵元数 (N_rx × N_ry)
M       = 50        快拍数
c       = 3e8       m/s
```

---

*本文档与 [3D_AoA_Estimation_Algorithm.md](3D_AoA_Estimation_Algorithm.md) 及 [Reflection_Parameter_Estimation.md](Reflection_Parameter_Estimation.md) 共同构成盲几何重建第一阶段（信号 → 角度 + 时延 + 能量）的完整算法体系。*
