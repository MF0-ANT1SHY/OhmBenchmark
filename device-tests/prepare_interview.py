import pathlib,shutil,subprocess,sys,json
root=pathlib.Path(__file__).resolve().parents[1];host=root/'hosts/interviewapp'
case,variant=sys.argv[1:3]
subprocess.run(['git','-C',str(host),'checkout','--detach',f'case/{case}/{variant}'],check=True)
utils=host/'features/home/src/main/ets/utils'
for name in ['OhmProbe.ets','InterviewBench.ets']:shutil.copy(root/'device-tests'/name,utils/name)
if case=='interviewapp_response_log_full_stringify':
    p=utils/'InterviewBench.ets';p.write_text(p.read_text(encoding='utf-8').replace('hdHttp','ohmHttp'),encoding='utf-8')
    p=host/'commons/basic/src/main/ets/utils/request.ets';s=p.read_text(encoding='utf-8')
    s="import hiTraceMeter from '@ohos.hiTraceMeter';\n"+s
    lines=s.splitlines();updated=[]
    for line in lines:
        if 'logger.info(fullUrl,' in line:updated.append("          hiTraceMeter.startTrace('OHMB/response_logging', 1);")
        updated.append(line)
        if 'logger.info(fullUrl,' in line:updated.append("          hiTraceMeter.finishTrace('OHMB/response_logging', 1);")
    s='\n'.join(updated)+"\nexport const ohmHttp = new HdHttp({baseURL: 'http://127.0.0.1:18766/'});\n"
    p.write_text(s,encoding='utf-8')
    p=host/'commons/basic/Index.ets';p.write_text(p.read_text(encoding='utf-8')+"\nexport { ohmHttp } from './src/main/ets/utils/request';\n",encoding='utf-8')
p=host/'features/home/Index.ets';p.write_text(p.read_text(encoding='utf-8')+"\nexport { runInterviewBench } from './src/main/ets/utils/InterviewBench';\n",encoding='utf-8')
p=host/'products/phone/src/main/ets/phoneability/PhoneAbility.ets';s=p.read_text(encoding='utf-8')
s=s.replace('onNewWant(want: Want, launchParam: AbilityConstant.LaunchParam): void {', '''onNewWant(want: Want, launchParam: AbilityConstant.LaunchParam): void {
    if (want.parameters && want.parameters['bench']) {
      const name = want.parameters['bench'].toString();
      import('@itcast/home').then((bench) => { bench.runInterviewBench(this.context, name); });
      return;
    }
''');p.write_text(s,encoding='utf-8')
subprocess.run(['git','-C',str(host),'add','features/home','products/phone/src/main','commons/basic/Index.ets','commons/basic/src/main/ets/utils/request.ets'],check=True)
subprocess.run(['git','-C',str(host),'commit','-m',f'test({case}): add real business method probe for {variant}'],check=True)
out=root/'device-tests/patches'/case;out.mkdir(parents=True,exist_ok=True)
(out/f'{variant}.patch').write_bytes(subprocess.check_output(['git','-C',str(host),'diff','HEAD~1','HEAD']))
