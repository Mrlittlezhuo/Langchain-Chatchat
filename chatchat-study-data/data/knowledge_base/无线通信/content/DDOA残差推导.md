### 4.2 DDOA 集群协同深度残差雅可比推导 (Jacobian of Depth Lock)

在全局目标函数中，单站 AoA 缺乏深度信息。DDOA (Differential Distance of Arrival) 利用无人机集群的时钟同步与星型拓扑（以 UAV 1 为参考节点），通过作差彻底消去了公共的“基站-反射点”光程，为反射点 $\mathbf{rsp}_n$ 提供了极其刚性的深度锁定约束。

#### 1. 残差方程定义
对于第 $n$ 个反射点，集群中剩余的 $K-1$ 架无人机 ($i \in \{2, 3, \dots, K\}$) 相对于参考无人机 1 产生的 DDOA 残差向量 $\mathbf{e}_{DDOA}(n) \in \mathbb{R}^{K-1}$ 定义为：

$$
\mathbf{e}_{DDOA}(n) = \begin{bmatrix}
(\|\mathbf{rsp}_n - \mathbf{p}_2\| - \|\mathbf{rsp}_n - \mathbf{p}_1\|) - \Delta \hat{d}_{21,n} \\
(\|\mathbf{rsp}_n - \mathbf{p}_3\| - \|\mathbf{rsp}_n - \mathbf{p}_1\|) - \Delta \hat{d}_{31,n} \\
\vdots \\
(\|\mathbf{rsp}_n - \mathbf{p}_K\| - \|\mathbf{rsp}_n - \mathbf{p}_1\|) - \Delta \hat{d}_{K1,n}
\end{bmatrix}
$$

其中，$\Delta \hat{d}_{i1, n}$ 为前端信号处理提取的 DDOA 观测常量；无人机位置 $\mathbf{p}_i$、$\mathbf{p}_1$ 为已知常量。该残差项**唯一依赖**的状态变量是第 $n$ 个反射点的位置 $\mathbf{rsp}_n$。

#### 2. 解析雅可比推导
我们需要求解目标为残差向量对状态变量的雅可比矩阵：
$$ \mathbf{J}_{DDOA, \mathbf{rsp}_n}^{(n)} = \frac{\partial \mathbf{e}_{DDOA}(n)}{\partial \mathbf{rsp}_n} \in \mathbb{R}^{(K-1) \times 3} $$

为了推导单行的偏导数，我们先引入中间变量——无人机 $k$ 到反射点 $n$ 的理论空间距离标量：
$$ D_{k,n} = \|\mathbf{rsp}_n - \mathbf{p}_k\| = \sqrt{(\mathbf{rsp}_n - \mathbf{p}_k)^T (\mathbf{rsp}_n - \mathbf{p}_k)} $$

根据向量微积分，距离标量对空间坐标向量的偏导数为理论预测方向向量的转置（行向量）：
$$ \frac{\partial D_{k,n}}{\partial \mathbf{rsp}_n} = \frac{(\mathbf{rsp}_n - \mathbf{p}_k)^T}{\|\mathbf{rsp}_n - \mathbf{p}_k\|} = \mathbf{u}_{pred, k,n}^T $$

那么，对于第 $i$ 行的标量残差方程 $e_i = D_{i,n} - D_{1,n} - \Delta \hat{d}_{i1,n}$，其关于 $\mathbf{rsp}_n$ 的偏导数为两个方向向量之差：
$$ \frac{\partial e_i}{\partial \mathbf{rsp}_n} = \mathbf{u}_{pred, i,n}^T - \mathbf{u}_{pred, 1,n}^T $$

将所有 $K-1$ 行拼接在一起，我们得到了极为工整优雅的**DDOA 解析雅可比矩阵**：

$$
\mathbf{J}_{DDOA, \mathbf{rsp}_n}^{(n)} = 
\begin{bmatrix}
\mathbf{u}_{pred, 2,n}^T - \mathbf{u}_{pred, 1,n}^T \\
\mathbf{u}_{pred, 3,n}^T - \mathbf{u}_{pred, 1,n}^T \\
\vdots \\
\mathbf{u}_{pred, K,n}^T - \mathbf{u}_{pred, 1,n}^T
\end{bmatrix} \in \mathbb{R}^{(K-1) \times 3}
$$

#### 3. 与全局优化目标的耦合分析 (Hessian Assembly)

推导雅可比的最终目的是为了组装正规方程。在全局目标中，DDOA 块贡献的 Hessian 矩阵增量为：
$$ \mathbf{H}_{DDOA}^{(n)} = (\mathbf{J}_{DDOA, \mathbf{rsp}_n}^{(n)})^T \mathbf{\Omega}_{DDOA} \mathbf{J}_{DDOA, \mathbf{rsp}_n}^{(n)} \in \mathbb{R}^{3 \times 3} $$

**此处是算法核心创新点的落脚处：** 
由于采用了星型拓扑作差，误差具有强共模相关性，这体现在上一节定义的密集非对角信息矩阵 $\mathbf{\Omega}_{DDOA} \in \mathbb{R}^{(K-1) \times (K-1)}$ 中。
在此组装过程中，高维的雅可比被 $\mathbf{\Omega}_{DDOA}$ 在矩阵内部进行了交叉权重分配。这在数学上保证了：我们既利用了作差模型消去未知发射时间 $t_0$，又在优化端彻底解耦了参考站带来的相关性噪声。

#### 4. 几何零空间互补分析 (Null Space Breaking)

*   在上一节中我们证明，AoA 的雅可比 $(\mathbf{I}_3 - \mathbf{u}_{pred} \mathbf{u}_{pred}^T)$ 是一个正交投影，其梯度在径向（视线深度方向）恒等于 $0$。
*   现在观察 DDOA 雅可比的行向量：$(\mathbf{u}_{pred, i,n}^T - \mathbf{u}_{pred, 1,n}^T)$。
*   **物理意义**：当两架无人机具有基线（即 $\mathbf{p}_i \neq \mathbf{p}_1$，导致视角 $\mathbf{u}_{pred, i,n} \neq \mathbf{u}_{pred, 1,n}$）时，这两个单位向量相减产生的梯度差向量，**恰好指向深度方向！**
*   **结论**：DDOA 提供的这组雅可比，完美地填补了 AoA 的径向零空间。两者相加构造的联合 Hessian 矩阵将变为满秩（Full Rank），系统由此彻底获得了 3D 空间内的全局可观测性。