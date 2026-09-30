import pathlib,shutil,subprocess,sys,json
root=pathlib.Path(__file__).resolve().parents[1];host=root/'hosts/interviewapp'
case,variant=sys.argv[1:3]
subprocess.run(['git','-C',str(host),'checkout','--detach',f'case/{case}/{variant}'],check=True)
utils=host/'features/home/src/main/ets/utils'
for name in ['OhmProbe.ets','InterviewBench.ets']:shutil.copy(root/'device-tests'/name,utils/name)
p=host/'features/home/Index.ets';p.write_text(p.read_text()+"\nexport { runInterviewBench } from './src/main/ets/utils/InterviewBench';\n")
p=host/'products/phone/src/main/ets/phoneability/PhoneAbility.ets';s=p.read_text()
s="import { runInterviewBench } from '@itcast/home';\n"+s
s=s.replace('onNewWant(want: Want, launchParam: AbilityConstant.LaunchParam): void {', '''onNewWant(want: Want, launchParam: AbilityConstant.LaunchParam): void {
    if (want.parameters && want.parameters['bench']) {
      runInterviewBench(this.context, want.parameters['bench'].toString());
      return;
    }
''');p.write_text(s)
subprocess.run(['git','-C',str(host),'add','features/home','products/phone/src/main'],check=True)
subprocess.run(['git','-C',str(host),'commit','-m',f'test({case}): add real business method probe for {variant}'],check=True)
out=root/'device-tests/patches'/case;out.mkdir(parents=True,exist_ok=True)
(out/f'{variant}.patch').write_bytes(subprocess.check_output(['git','-C',str(host),'diff','HEAD~1','HEAD']))
