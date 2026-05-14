# 提示词模板

提示词模板存放于本目录。

## 结构：
- `s2_normalize_prompt.md`: S2 Flash 标准化提示词
- `s4_freeze_prompt.md`: S4 ID 冻结提示词  
- `s5_alias_prompt.md`: S5 别名检测提示词

所有提示词参数化：使用 `{namespace_list}`, `{semantic_type_list}`, `{domain_description}` 等占位符。

## 关键原则：
1. Flash 提示词必须约束而非释放创造力
2. 仅使用可信的关系类型
3. 输出格式：JSON 数组（不要用 markdown 包裹）
4. 置信度 < 0.85 → needs_review = True
5. 保守合并：宁可错误合并，也不要重复留存
