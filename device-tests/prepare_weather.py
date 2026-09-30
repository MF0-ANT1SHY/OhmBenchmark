import pathlib,subprocess,sys,re
root=pathlib.Path(__file__).resolve().parents[1];host=root/'hosts/weatherassistant'
case,variant=sys.argv[1:3]
subprocess.run(['git','-C',str(host),'checkout','--detach',f'case/{case}/{variant}'],check=True)
ets=host/'alatus/src/main/ets';(ets/'utils').mkdir(exist_ok=True)
for name in ['OhmProbe.ets','WeatherBench.ets']:(ets/'utils'/name).write_bytes((root/'device-tests'/name).read_bytes())
p=ets/'viewmodel/getWeatherUtil.ets';s=p.read_text(encoding='utf-8')
s=re.sub(r'let url = `https://restapi[^;]+;',"let url = `http://127.0.0.1:18767/weather?city=${cityCode}`;",s)
p.write_text(s,encoding='utf-8')
p=ets/'alatusability/AlatusAbility.ets';s=p.read_text(encoding='utf-8')
s="import { runWeatherBench } from '../utils/WeatherBench';\n"+s
s=s.replace('export default class AlatusAbility extends UIAbility {','''export default class AlatusAbility extends UIAbility {
  onNewWant(want: Want): void {
    if (want.parameters && want.parameters['bench']) runWeatherBench(this.context,want.parameters['bench'].toString());
  }
''');p.write_text(s,encoding='utf-8')
subprocess.run(['git','-C',str(host),'add','alatus/src/main'],check=True)
subprocess.run(['git','-C',str(host),'commit','-m',f'test({case}): measure native HTTP session lifecycle for {variant}'],check=True)
out=root/'device-tests/patches'/case;out.mkdir(parents=True,exist_ok=True)
(out/f'{variant}.patch').write_bytes(subprocess.check_output(['git','-C',str(host),'diff','HEAD~1','HEAD']))
