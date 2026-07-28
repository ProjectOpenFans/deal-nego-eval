# 谈判评测控制台

中文三栏式评测查看器：

- 左侧选择 Case、实验组和 rerun；
- 中间查看完整谈判历史与每轮结构化 offer；
- 右侧查看结构化 initial input、Case fixture、M1–M12、judge samples、
  最终 deal、模型路由和全部运行参数。

## 刷新数据

```bash
cd ..
python scripts/build_viewer_data.py \
  --results results/clean-coolwei-glm52-qwen36 \
  --endpoint-status configs/model-endpoint-status.json \
  --output viewer/public/data/report.json
cd viewer
npm test
npm run dev
```

Viewer 只读取当前 Coolwei GLM / Qwen 结果目录，不混入任何历史样本。
