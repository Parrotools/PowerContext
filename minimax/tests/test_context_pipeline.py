"""import → context 全链路测试(临时 home,真实嵌入式 seekdb;PowerContext 不可达时自动降级)。"""

import shutil
from pathlib import Path

from sddctx.config import Settings
from sddctx.context_builder import build_context
from sddctx.importer import run_import

SPEC_TEXT = """# SPEC-100 查询规格

- 编号: SPEC-100
- 状态: 有效
- 适用模块: demo.service

## 条目

- SPEC-100-1: 查询接口支持 min_total 参数(Decimal),含边界过滤。
- SPEC-100-2: 结果按创建时间升序。
"""


def make_settings(tmp_path: Path) -> Settings:
    (tmp_path / "specs").mkdir()
    (tmp_path / "specs" / "SPEC-100-查询规格.md").write_text(SPEC_TEXT, encoding="utf-8")
    src = tmp_path / "sample-project" / "src" / "demo"
    src.mkdir(parents=True)
    (src / "service.py").write_text(
        '"""查询服务。\n\n订单查询 min_total 查询接口。\n"""\n\n\ndef query(min_total=None):\n    return []\n',
        encoding="utf-8",
    )
    tests_dir = tmp_path / "sample-project" / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_query.py").write_text(
        "def test_min_total_filter():\n    assert query(min_total=1) == []\n",
        encoding="utf-8",
    )
    settings = Settings.load()
    object.__setattr__(settings, "home", tmp_path)
    object.__setattr__(settings, "seekdb_path", tmp_path / ".sddctx-data" / "seekdb")
    object.__setattr__(settings, "db_query_log", tmp_path / "records" / "db-query-log.md")
    object.__setattr__(settings, "powercontext_log", tmp_path / "records" / "powercontext-log.md")
    return settings


def test_import_then_context_end_to_end(tmp_path: Path):
    settings = make_settings(tmp_path)
    result, _report = run_import(settings)
    assert result.assets_upserted == 5  # 1 spec_file + 2 spec_entry + 1 code + 1 test
    assert result.counts["spec_entry"] == 2

    context = build_context(settings, "为查询接口增加 min_total 最小金额筛选", use_state=False)
    entry_sources = [item.path for item in context.spec_entries]
    assert any("SPEC-100-1" in source for source in entry_sources)
    code_paths = [item.path for item in context.code]
    assert any(path.endswith("service.py") for path in code_paths)
    test_paths = [item.path for item in context.tests]
    assert any(path.endswith("test_query.py") for path in test_paths)
    # 干扰条目(排序条目)不应对该任务排在首位
    assert "SPEC-100-1" in entry_sources[0]
    # markdown 输出带真实来源标注
    markdown = context.to_markdown()
    assert "specs/SPEC-100-查询规格.md#SPEC-100-1" in markdown
    assert "来源:" in markdown


def test_spec_update_reimport_changes_context(tmp_path: Path):
    settings = make_settings(tmp_path)
    run_import(settings)
    context_v1 = build_context(settings, "查询接口 min_total 含边界", use_state=False)
    assert all("v2" not in item.content for item in context_v1.spec_entries)

    spec_path = tmp_path / "specs" / "SPEC-100-查询规格.md"
    spec_path.write_text(SPEC_TEXT.replace(
        "- SPEC-100-1: 查询接口支持 min_total 参数(Decimal),含边界过滤。",
        "- SPEC-100-1: 查询接口支持 min_total 参数(Decimal),含边界过滤。【v2 修订】",
    ), encoding="utf-8")
    run_import(settings)

    context_v2 = build_context(settings, "查询接口 min_total 含边界", use_state=False)
    target = next(item for item in context_v2.spec_entries if "SPEC-100-1" in item.path)
    assert "v2 修订" in target.content
    assert target.version == 2
