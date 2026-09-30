import pathlib,shutil,subprocess,sys
root=pathlib.Path(__file__).resolve().parents[1];host=root/'hosts/wanharmony'
case,variant=sys.argv[1:3]
subprocess.run(['git','-C',str(host),'checkout','--detach',f'case/{case}/{variant}'],check=True)
ets=host/'entry/src/main/ets'
shutil.copy(root/'device-tests/OhmProbe.ets',ets/'utils/OhmProbe.ets')
p=ets/'entryability/EntryAbility.ets';s=p.read_text(encoding='utf-8')
s="import { WebData } from '../data/WebData';\n"+s
s=s.replace('export default class EntryAbility extends UIAbility {', '''export default class EntryAbility extends UIAbility {
  onNewWant(want: Want): void {
    if (want.parameters && want.parameters['bench']) {
      const records: WebData[] = [];
      for (let i=0;i<50000;i++) records.push(new WebData('https://example.org/article/'+i, 'HarmonyOS engineering article '+i, '2026/09/30 12:00:00', false));
      AppStorage.SetOrCreate('historyList', records);
      AppStorage.SetOrCreate('ohmOpenHistory', true);
    }
  }
''');p.write_text(s,encoding='utf-8')
p=ets/'pages/Index.ets';s=p.read_text(encoding='utf-8').replace('struct Index {', '''struct Index {
  @StorageLink('ohmOpenHistory') @Watch('openMeasuredHistory') ohmOpenHistory: boolean = false;
  openMeasuredHistory(): void {
    if (this.ohmOpenHistory) this.pathStack.pushPathByName('HistoryPage', null);
  }
''');p.write_text(s,encoding='utf-8')
p=ets/'pages/HistoryPage.ets';s=p.read_text(encoding='utf-8')
s="import { common } from '@kit.AbilityKit';\nimport { OhmProbe } from '../utils/OhmProbe';\n"+s
start=s.index('  aboutToAppear(): void {');end=s.index('\n  build()',start)
original=s[start:end];body=original[original.index('{')+1:original.rfind('}')]
s=s[:start]+'''  aboutToAppear(): void {
    OhmProbe.measure(getContext(this) as common.UIAbilityContext, 'wanharmony_history_log_materialization',
      async (): Promise<void> => {}, async (): Promise<number> => {
'''+body+'''
        return this.historyList.length;
      });
  }
'''+s[end:];p.write_text(s,encoding='utf-8')
subprocess.run(['git','-C',str(host),'add','entry/src/main'],check=True)
subprocess.run(['git','-C',str(host),'commit','-m',f'test({case}): instrument actual history page logging for {variant}'],check=True)
out=root/'device-tests/patches'/case;out.mkdir(parents=True,exist_ok=True)
(out/f'{variant}.patch').write_bytes(subprocess.check_output(['git','-C',str(host),'diff','HEAD~1','HEAD']))
