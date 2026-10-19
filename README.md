# Biohazard Tide: Plague Dynasty / 生化狂潮：瘟疫王朝

《铁锈战争》（Rusted Warfare）模组「生化狂潮：瘟疫王朝」的续作。
原作者：蚟醛钯烨（已获授权）。

当前版本基于 v1.97 经典完美版修复，可在铁锈战争 **v1.15** 正常加载。

## 下载与安装

1. 到 [Releases](https://github.com/Zhou-Jin-Feng/Biohazard-Tide-Plague-Dynasty/releases) 下载最新的 `.rwmod` 文件。
2. 放进游戏目录下的 `mods/units/` 文件夹。
3. 启动游戏，在模组列表中启用即可。

## 目录结构

```
mod/            模组源文件（ini、贴图、音效），打包时就是 .rwmod 的内容
  mod-info.txt  模组名称、简介
  人类/          人类阵营单位
  僵尸/          僵尸阵营单位
  阵营选择/      开局阵营选择
tools/pack.py   打包脚本
dist/           打包输出（不提交，发布到 Releases）
```

## 打包

需要 Python 3.8+：

```bash
python tools/pack.py
```

生成 `dist/[生化狂潮-瘟疫王朝].rwmod`，复制到游戏的 `mods/units/` 即可测试。
也可以用 `-o` 指定输出路径。

## 修改注意事项

- ini 文件使用 UTF-8 编码保存。
- 贴图、音效引用的文件名要和实际文件完全一致；改了文件名记得同步修改 ini 中的引用。
- 改完后进游戏检查模组是否报错。报错详情可以在游戏目录的 `lastrun.log` 中搜索 `Error loading unit`。
