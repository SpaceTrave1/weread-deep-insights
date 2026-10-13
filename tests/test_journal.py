"""Journal regressions use invented records only, with network/auth forbidden."""
import copy
import json
import tempfile
from html.parser import HTMLParser
from pathlib import Path

from test_report import OfflineTest, complete_data
from test_history import history_data
from test_evolution import extraction_result, comparison_result
from scripts.evidence_bundle import prepare_bundle, write_json
from scripts.history import HistoryStore
from scripts.evolution_analysis import prepare_extraction, merge_extractions, prepare_comparison, merge_comparisons
from scripts.journal_rendering import render_journal, note_library, json_script, date
from scripts.render_journal import main
from scripts.evolution_workflow import record_feedback
from test_llm import example_result


class ParsedHTML(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.ids=[];self.external=[];self.scripts=[];self.current_script=None;self.payload=''
        self.feed(text)
    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs)
        if 'id' in attrs:self.ids.append(attrs['id'])
        for key in ('src','href'):
            if attrs.get(key,'').startswith(('http:','https:','//')):self.external.append(attrs[key])
        if tag=='script':
            self.scripts.append(attrs);self.current_script=attrs.get('id')
    def handle_endtag(self,tag):
        if tag=='script':self.current_script=None
    def handle_data(self,text):
        if self.current_script=='journal-data':self.payload+=text


class JournalTests(OfflineTest):
    def setUp(self):
        super().setUp()
        self.temp=tempfile.TemporaryDirectory(prefix='synthetic-journal-',dir=Path(__file__).parent)
        self.addCleanup(self.temp.cleanup)
        self.directory=Path(self.temp.name)
        self.store=HistoryStore(self.directory/'history')
        self.addCleanup(self.store.close)
        self.data=history_data()
        self.store.ingest(self.data)
        self.history=self.store.export()
        self.bundle=prepare_bundle(self.data,'合成完整报告')
        self.baseline=self.bundle['baseline_report']
        plan=prepare_extraction(self.history)
        extracted=merge_extractions(self.history,plan,[extraction_result(r) for r in plan['requests']])
        compared=prepare_comparison(self.history,extracted)
        self.evolution=merge_comparisons(self.history,compared,[comparison_result(r) for r in compared['requests']])

    def render(self,**kwargs):
        options=dict(evidence=self.bundle['evidence'],history=self.history,evolution=self.evolution)
        options.update(kwargs)
        return render_journal(self.baseline,**options)

    def test_five_modules_preserve_baseline_and_share_question_archive(self):
        text=self.render();parsed=ParsedHTML(text)
        for key in ('overview','map','notes','thinking','inspiration','coverage','theme-view','time-view'):
            self.assertIn(key,parsed.ids)
        self.assertEqual(len(parsed.ids),len(set(parsed.ids)))
        for value in ('合成科学','作者线索','年度阅读','个人点评','规则参考','观点档案实际分析','阅读集中度与覆盖提醒'):
            self.assertIn(value,text)
        self.assertIn('data-open-archive=',text)
        self.assertNotIn('<h2>严格诊断</h2>',text)
        self.assertNotIn('<h2>价值观、焦虑',text)

    def test_no_external_resources_and_feedback_matches_existing_import(self):
        parsed=ParsedHTML(self.render())
        self.assertEqual(parsed.external,[])
        self.assertEqual(len(parsed.scripts),2)
        payload=json.loads(parsed.payload)
        for row in payload['feedback'].values():
            entry=dict(row,status='confirmed',explanation='合成用户反馈')
            saved=record_feedback(self.store,self.evolution,entry)
            self.assertEqual(saved['status'],'confirmed')
            self.assertIn('reviewed_explanation',saved)

    def test_html_and_json_note_injection_is_inert(self):
        attack='</script><script>alert("synthetic")</script><img src=x onerror=alert(1)> & \u2028'
        self.data['notebooks']['bookNotes'][0]['reviews'][0]['content']=attack
        self.data['generatedAt']='2026-02-01T00:00:00+08:00'
        self.store.ingest(self.data)
        history=self.store.export()
        report=copy.deepcopy(self.baseline);report['title']=attack
        text=render_journal(report,history=history)
        parsed=ParsedHTML(text)
        self.assertEqual(len(parsed.scripts),2)
        self.assertNotIn('<img src=x',text)
        self.assertIn(attack.strip(),[n['text'] for n in json.loads(parsed.payload)['notes']])
        self.assertEqual(json.loads(json_script({'x':attack}))['x'],attack)

    def test_no_evolution_result_is_an_explicit_empty_state(self):
        text=render_journal(self.baseline,evidence=self.bundle['evidence'])
        self.assertIn('尚未导入观点演化结果',text)
        self.assertIn('不能据此认定观点没有变化',text)
        self.assertEqual(json.loads(ParsedHTML(text).payload)['feedback'],{})

    def test_bad_dataset_and_invalid_quotes_rejected(self):
        mismatched=copy.deepcopy(self.evolution)
        mismatched['history']['dataset_id']='different'
        with self.assertRaises(ValueError):self.render(evolution=mismatched)

    def test_fragments_reassemble_into_whole_notes(self):
        data=complete_data()
        data['notebooks']['bookNotes'][0]['reviews'][0]['content']='合成较长文本。'*80
        bundle=prepare_bundle(data,'合成',fragment_chars=100)
        notes=note_library(None,bundle['evidence'])
        self.assertEqual(len(notes),5)
        self.assertIn('合成较长文本。'*80,[n['text'] for n in notes])

    def test_separate_snapshots_are_visible_and_new_basis_requires_binding(self):
        basis={key:self.baseline[key] for key in ('basis','annual','coverage')}
        text=self.render(current_basis=basis)
        self.assertIn(date(self.history['observed_at']),text)
        wrong=copy.deepcopy(basis);wrong['coverage']['notesComplete']=not wrong['coverage']['notesComplete']
        with self.assertRaises(ValueError):self.render(current_basis=wrong)
        with self.assertRaises(ValueError):render_journal(self.baseline,current_basis=basis)

    def test_unknown_dates_are_not_invented(self):
        self.assertEqual(date(None),'日期未知')
        self.assertEqual(date('not a date'),'日期未知')
        self.assertEqual(date('2025-01-01T23:30:00+00:00'),'2025-01-02')

    def test_evolution_review_coverage_excludes_processed_underlines(self):
        self.assertEqual(self.evolution['coverage']['extraction']['complete_notes'],5)
        text=self.render()
        self.assertIn('观点档案实际分析 2 条个人点评',text)
        self.assertIn('完整声明处理 2/2 条选中个人点评',text)
        self.assertNotIn('实际分析 5 条个人点评',text)

    def test_unknown_official_metrics_and_impossible_completion_are_not_zero_or_scores(self):
        report=copy.deepcopy(self.baseline)
        report['basis'].update(timeAvailable=False,daysAvailable=False,bookCountsAvailable=False)
        text=render_journal(report,evidence=self.bundle['evidence'])
        self.assertIn('<b class="time-value">未取得</b>',text)
        report['basis'].update(bookCountsAvailable=True,booksRead=2,booksFinished=5)
        text=render_journal(report,evidence=self.bundle['evidence'])
        self.assertIn('官方读完比例 <b>未取得</b>',text)
        self.assertNotIn('250.0%',text)

    def test_unconfirmed_shelf_is_not_a_valid_zero(self):
        report=copy.deepcopy(self.baseline)
        report['basis'].update(shelfTotal=0,shelfBooks=0,albums=0,mpCount=0)
        summary=report['coverage']['groups']['汇总与目录']
        summary['success']-=1;summary['failed']+=1
        text=render_journal(report,evidence=self.bundle['evidence'])
        self.assertIn('未确认<span>个书架条目',text)
        self.assertNotIn('0<span>个书架条目',text)

    def test_semantic_input_is_validated_against_its_exact_bundle(self):
        write_json(self.directory/'bundle.json',self.bundle)
        subset=prepare_bundle(self.data,'合成',max_notes=1)
        write_json(self.directory/'subset.json',subset)
        write_json(self.directory/'result.json',example_result(subset))
        destination=self.directory/'output'
        args=['--input',str(self.directory/'bundle.json'),'--semantic-input',str(self.directory/'subset.json'),
              '--analysis-result',str(self.directory/'result.json'),'--output-dir',str(destination)]
        self.assertEqual(main(args),0)
        self.assertIn('完整声明处理 1/1 条选中笔记',(destination/'index.html').read_text(encoding='utf-8'))
        args.remove('--semantic-input');args.remove(str(self.directory/'subset.json'))
        args[-1]=str(self.directory/'invalid-output')
        self.assertEqual(main(args),2)
        self.assertFalse((self.directory/'invalid-output').exists())

    def test_offline_cli_writes_both_and_preserves_old_inputs(self):
        before=copy.deepcopy(self.bundle)
        write_json(self.directory/'bundle.json',self.bundle)
        write_json(self.directory/'history.json',self.history)
        write_json(self.directory/'evolution.json',self.evolution)
        destination=self.directory/'output'
        code=main(['--input',str(self.directory/'bundle.json'),'--history-input',str(self.directory/'history.json'),
                   '--evolution-report',str(self.directory/'evolution.json'),'--output-dir',str(destination)])
        self.assertEqual(code,0)
        self.assertTrue((destination/'index.html').exists())
        markdown=(destination/'weread_deep_report.md').read_text(encoding='utf-8')
        self.assertIn('## 数据基础',markdown)
        self.assertIn('我的思考：时间视图',markdown)
        self.assertEqual(self.bundle,before)

    def test_invalid_input_does_not_write_any_report(self):
        write_json(self.directory/'bundle.json',self.bundle)
        bad=copy.deepcopy(self.evolution);bad['trajectories'][0]['quotes'][0]['text']='不存在的合成引用'
        write_json(self.directory/'bad.json',bad)
        destination=self.directory/'output'
        code=main(['--input',str(self.directory/'bundle.json'),'--evolution-report',str(self.directory/'bad.json'),'--output-dir',str(destination)])
        self.assertEqual(code,2)
        self.assertFalse(destination.exists())
