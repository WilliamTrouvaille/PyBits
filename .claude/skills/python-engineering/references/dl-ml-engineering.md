# DL/ML 工程实践

> 本文件范围：DL/ML 训练工程实践（设备管理、数据加载、训练循环、检查点、混合精度、内存、可复现性、日志）。
> 不在本文件范围：模型架构设计、损失函数选择、超参数调优策略、数学推导。

## 设备管理

- 自动检测设备：
  ```python
  device = torch.device(
      "cuda" if torch.cuda.is_available()
      else "mps" if torch.backends.mps.is_available()
      else "cpu"
  )
  ```
- 所有张量和模块统一使用 `.to(device)`，避免设备不匹配的静默错误。
- 多 GPU 场景简述：`nn.DataParallel`（快速原型）→ `torch.distributed`（生产级）。本文件不展开分布式训练教程。

## 数据加载

- DataLoader 调优要点：
  - `num_workers`：设为 CPU 核心数的 1/4 ~ 1/2，过高反而拖慢。
  - `pin_memory=True`：使用 GPU 时启用，加速 CPU→GPU 传输。
  - `prefetch_factor`：默认 2，数据加载为瓶颈时调高。
- `Dataset` vs `IterableDataset`：前者支持随机访问和 len，后者适合流式/超大规模数据。
- 大规模数据优先使用内存映射（如 `numpy.memmap`），避免一次性加载。
- 懒加载 tokenizer、processor 等昂贵组件，仅在首次使用时初始化。

## 训练循环

- 标准 epoch/step 结构：
  ```python
  for epoch in range(num_epochs):
      model.train()
      for batch in train_loader:
          loss = forward_backward_step(model, batch)
      model.eval()
      with torch.inference_mode():
          validate(model, val_loader)
  ```
- 评估阶段用 `torch.inference_mode()` 而非 `torch.no_grad()`（更高效）。
- 梯度裁剪：`torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm)`，防止梯度爆炸。
- NaN 检测：训练中若 loss 出现 NaN，立即停止并报告，不静默继续。
- 日志粒度：epoch 级适合小数据集，step 级适合大数据集。按数据规模选择。

## 检查点与恢复

- 保存模式：
  ```python
  torch.save({
      "model": model.state_dict(),
      "optimizer": optimizer.state_dict(),
      "scheduler": scheduler.state_dict() if scheduler else None,
      "epoch": epoch,
      "rng_state": torch.cuda.get_rng_state(),
  }, path)
  ```
- 恢复时依次还原：model → optimizer → scheduler → RNG state，确保可复现。
- 保留 best-model（按验证指标）和 last-model 两个检查点，磁盘充裕时两者都存。
- 大模型可考虑异步保存，避免阻塞训练循环。

## 混合精度

- 基本模式：
  ```python
  with torch.amp.autocast(device_type="cuda"):
      output = model(input)
      loss = criterion(output, target)
  scaler.scale(loss).backward()
  scaler.unscale_(optimizer)          # 必须在梯度裁剪前 unscale
  torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm)
  scaler.step(optimizer)
  scaler.update()
  ```
- BF16 可用（Ampere+架构）时优先于 FP16：无需 GradScaler，数值更稳定。
- 常见陷阱：忘记 `scaler.unscale_()` 就做梯度裁剪，会得到错误的梯度范数。

## 内存管理

- 梯度累积：用 `loss / accumulation_steps` 模拟更大 batch size。
- Activation checkpointing：`torch.utils.checkpoint.checkpoint`，用计算换内存。
- 大模型 CPU offloading：`torch.cuda.empty_cache()` 定期清理，或将部分参数暂存 CPU。
- 内存诊断：`torch.cuda.memory_summary()` 和 `torch.cuda.max_memory_allocated()` 定位峰值。

## 可复现性

- 种子设置覆盖所有随机源：
  ```python
  import random, numpy as np
  random.seed(seed)
  np.random.seed(seed)
  torch.manual_seed(seed)
  torch.cuda.manual_seed_all(seed)
  ```
- 严格模式：
  ```python
  torch.use_deterministic_algorithms(True)
  torch.backends.cudnn.deterministic = True
  ```
  严格确定性可能降低性能，部分算子（如 scatter_add）会报错或需要替代实现。
- 已知非确定性算子：`scatter_add`、`interpolate`（部分模式），使用时记录在文档中。
- 无法完全确定时：记录方差边界，用多次运行取均值验证稳定性。

## 日志与横幅

- 训练启动横幅（提取自通用日志规范，用于训练场景）：
  ```python
  logger.info("=" * 80)
  logger.info("开始训练!".center(80))
  logger.info(f"跟踪指标: '{self.metric_to_track}'")
  logger.info("=" * 80)
  ```
- 指标日志：训练起止、关键里程碑、异常路径必须记录。
- 检查点保存后确认日志：`logger.info(f"检查点已保存: {path}")`。
- 实验跟踪工具简要：wandb / TensorBoard 按项目惯例选择，本文件不指定。
