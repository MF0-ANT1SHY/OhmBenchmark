import pathlib,subprocess,sys
root=pathlib.Path(__file__).resolve().parents[1];host=root/'hosts/cloudmusic'
case,variant=sys.argv[1:3]
subprocess.run(['git','-C',str(host),'checkout','--detach',f'case/{case}/{variant}'],check=True)
manifest=host/'entry/src/main/module.json5'
import re
s=manifest.read_text(encoding='utf-8')
s,n=re.subn(r'\s*\{\s*"name"\s*:\s*"ohos.permission.SYSTEM_FLOAT_WINDOW"[\s\S]*?\n        \},','',s)
assert n==1, 'Expected exactly one floating-window permission'
manifest.write_text(s,encoding='utf-8')
ets=host/'entry/src/main/ets';(ets/'utils').mkdir(exist_ok=True)
for name in ['OhmProbe.ets','CloudBench.ets']:(ets/'utils'/name).write_bytes((root/'device-tests'/name).read_bytes())
p=ets/'entryability/EntryAbility.ets';s=p.read_text(encoding='utf-8')
s=s.replace('export default class EntryAbility extends UIAbility {','''export default class EntryAbility extends UIAbility {
  onNewWant(want: Want): void {
    if (want.parameters && want.parameters['bench']) {
      const name=want.parameters['bench'].toString();
      import('../utils/CloudBench').then((bench) => {bench.runCloudBench(this.context,name);});
    }
  }
''');p.write_text(s,encoding='utf-8')
if case=='cloudmusic_local_song_memory_filter':
    p=ets/'pages/Index.ets';s=p.read_text(encoding='utf-8')
    s=s.replace('struct Index {','''struct Index {
  @StorageLink('ohmLocalBench') @Watch('openLocalBench') ohmLocalBench: boolean = false;
  openLocalBench(): void {if(this.ohmLocalBench) this.pageInfos.pushPathByName('LocalSongPage',null);}
''');p.write_text(s,encoding='utf-8')
    p=ets/'pages/local/LocalSongPage.ets';s=p.read_text(encoding='utf-8')
    s="import { common } from '@kit.AbilityKit';\nimport { OhmProbe } from '../../utils/OhmProbe';\n"+s
    s=s.replace('    this.isLoading = false',"    this.isLoading = false\n    if(AppStorage.Get<boolean>('ohmLocalBench')) this.runLocalBench();",1)
    s=s.replace('  aboutToDisappear(): void {','''  private runLocalBench(): void {
    OhmProbe.measure(getContext(this) as common.UIAbilityContext,'cloudmusic_local_song_memory_filter',async (): Promise<void> => {
      await this.refreshList(); this.searchKeyword='song-00999';
      await new Promise<void>((resolve) => {setTimeout(resolve,500);});
    },async (): Promise<number> => {
      let total=0;
      for(let i=0;i<10;i++) {await this.handelSearch();total+=this.dataSourceFiltered.totalCount();}
      return total;
    });
  }
  aboutToDisappear(): void {''');p.write_text(s,encoding='utf-8')
subprocess.run(['git','-C',str(host),'add','entry/src/main'],check=True)
subprocess.run(['git','-C',str(host),'commit','-m',f'test({case}): measure original app business path for {variant}'],check=True)
out=root/'device-tests/patches'/case;out.mkdir(parents=True,exist_ok=True)
(out/f'{variant}.patch').write_bytes(subprocess.check_output(['git','-C',str(host),'diff','HEAD~1','HEAD']))
