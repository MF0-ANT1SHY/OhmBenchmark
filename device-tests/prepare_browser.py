import pathlib, subprocess, sys
root = pathlib.Path(__file__).resolve().parents[1]
host = root / 'hosts/browser'
case, variant = sys.argv[1:3]
subprocess.run(['git','-C',str(host),'checkout','--detach',f'case/{case}/{variant}'],check=True)
ets = host / 'entry/src/main/ets'
for name in ['OhmProbe.ets','BrowserBench.ets']:
    (ets/'utils'/name).write_bytes((root/'device-tests'/name).read_bytes())
p = ets/'entryability/EntryAbility.ets'
s = p.read_text(encoding='utf-8')
s = "import { Want } from '@kit.AbilityKit';\nimport { runBrowserBench } from '../utils/BrowserBench';\n" + s
s = s.replace('export default class EntryAbility extends UIAbility {', '''export default class EntryAbility extends UIAbility {
  onNewWant(want: Want): void {
    if (want.parameters && want.parameters['bench']) {
      runBrowserBench(this.context, want.parameters['bench'].toString());
    }
  }
''')
p.write_text(s,encoding='utf-8')
subprocess.run(['git','-C',str(host),'add','entry/src/main/ets'],check=True)
subprocess.run(['git','-C',str(host),'commit','-m',f'test({case}): add identical on-device measurement entry for {variant}'],check=True)
out=root/'device-tests/patches'/case
out.mkdir(parents=True,exist_ok=True)
(out/f'{variant}.patch').write_bytes(subprocess.check_output(['git','-C',str(host),'diff','HEAD~1','HEAD']))
