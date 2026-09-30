import pathlib, subprocess, sys
root=pathlib.Path(__file__).resolve().parents[1]
host=root/'hosts/sheafreader'
case,variant=sys.argv[1:3]
subprocess.run(['git','-C',str(host),'checkout','--detach',f'case/{case}/{variant}'],check=True)
ets=host/'entry/src/main/ets'
for name in ['OhmProbe.ets','SheafBench.ets']:
    (ets/'utils'/name).write_bytes((root/'device-tests'/name).read_bytes())
p=ets/'entryability/EntryAbility.ets'
s=p.read_text(encoding='utf-8')
s="import { runSheafBench } from '../utils/SheafBench';\n"+s
s=s.replace('onNewWant(want: Want, launchParam: AbilityConstant.LaunchParam): void {', '''onNewWant(want: Want, launchParam: AbilityConstant.LaunchParam): void {
    if (want.parameters && want.parameters['bench']) {
      runSheafBench(this.context, want.parameters['bench'].toString());
    }''')
p.write_text(s,encoding='utf-8')
if case=='sheafreader_article_list_foreach':
    s=p.read_text(encoding='utf-8').replace("runSheafBench(this.context, want.parameters['bench'].toString());", "AppStorage.SetOrCreate('ohmArticleBench', true);")
    p.write_text(s,encoding='utf-8')
    (ets/'utils/SheafUiBench.ets').write_bytes((root/'device-tests/SheafUiBench.ets').read_bytes())
    p=ets/'pages/Index.ets';s=p.read_text(encoding='utf-8')
    s="import { runSheafUiBench } from '../utils/SheafUiBench';\n"+s
    s=s.replace('struct Index {', '''struct Index {
  @StorageLink('ohmArticleBench') @Watch('startArticleBench') ohmArticleBench: boolean = false;
  startArticleBench(): void {
    if (this.ohmArticleBench) runSheafUiBench(getContext(this) as common.UIAbilityContext, this.store);
  }
''');p.write_text(s,encoding='utf-8')
    p=ets/'components/ArticleCards.ets';s=p.read_text(encoding='utf-8')
    s="import hiTraceMeter from '@ohos.hiTraceMeter';\n"+s
    s=s.replace('export struct ListCard {', '''export struct ListCard {
  aboutToAppear(): void {
    const count: number = (AppStorage.Get<number>('ohmArticleCount') || 0)+1;
    AppStorage.SetOrCreate('ohmArticleCount',count);
    hiTraceMeter.traceByValue('OHMB/ArticleCardCount',count);
  }
''');p.write_text(s,encoding='utf-8')
manifest=host/'entry/src/main/module.json5'
manifest.write_text(manifest.read_text(encoding='utf-8').replace('"deviceTypes": [','"deviceTypes": ["phone",'),encoding='utf-8')
subprocess.run(['git','-C',str(host),'add','entry/src/main'],check=True)
subprocess.run(['git','-C',str(host),'commit','-m',f'test({case}): add identical on-device measurement entry for {variant}'],check=True)
out=root/'device-tests/patches'/case
out.mkdir(parents=True,exist_ok=True)
(out/f'{variant}.patch').write_bytes(subprocess.check_output(['git','-C',str(host),'diff','HEAD~1','HEAD']))
