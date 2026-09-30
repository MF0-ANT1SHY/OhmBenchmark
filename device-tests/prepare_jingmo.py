import pathlib,subprocess,sys,json
root=pathlib.Path(__file__).resolve().parents[1]; host=root/'hosts/jingmo'
case,variant=sys.argv[1:3]
subprocess.run(['git','-C',str(host),'checkout','--detach',f'case/{case}/{variant}'],check=True)
ets=host/'products/default/src/main/ets'; (ets/'utils').mkdir(exist_ok=True)
(ets/'utils/OhmProbe.ets').write_bytes((root/'device-tests/OhmProbe.ets').read_bytes())
s=(root/'device-tests/JingmoBench.ets').read_text(encoding='utf-8')
if case=='jingmo_random_poem_orderby_random':
    action='''let count=0;
    for (let i=0;i<10;i++) { const poem = await dao.readRandomClassicPoem(); if (poem !== null) count++; }
    return count;'''
elif case=='jingmo_sync_page_reimport':
    s=s.replace('// EXTRA_IMPORT',"import DatasetViewModel from 'settings/src/main/ets/viewmodel/DatasetViewModel';")
    action='await DatasetViewModel.insertClassicPoemsToDb(poems); return poems.length;'
else:
    if variant=='unfixed':
        p=host/'features/classicalliterature/classicpoem/src/main/ets/database/ClassicPoemDao.ets'
        p.write_text(p.read_text(encoding='utf-8').replace('    DbUtil.objectiveRDB?.insert','    return DbUtil.objectiveRDB?.insert'),encoding='utf-8')
        action='await Promise.all(poems.map((p: ClassicPoem) => dao.createClassicPoem(p))); return poems.length;'
    else: action='await dao.createClassicPoems(poems); return poems.length;'
(ets/'utils/JingmoBench.ets').write_text(s.replace('// MEASURE_ACTION',action),encoding='utf-8')
p=ets/'entryability/EntryAbility.ets'; s=p.read_text(encoding='utf-8')
s="import { runJingmoBench } from '../utils/JingmoBench';\n"+s
s=s.replace('export default class EntryAbility extends UIAbility {', '''export default class EntryAbility extends UIAbility {
  onNewWant(want: Want): void {
    if (want.parameters && want.parameters['bench']) runJingmoBench(this.context, want.parameters['bench'].toString());
  }
''');p.write_text(s,encoding='utf-8')
p=host/'products/default/oh-package.json5'; d=json.loads(p.read_text(encoding='utf-8'))
d['dependencies'].update({'constants':'file:../../commons/constants','classicalliterature_classicpoem':'file:../../features/classicalliterature/classicpoem','settings':'file:../../features/settings'})
p.write_text(json.dumps(d,indent=2),encoding='utf-8')
subprocess.run(['git','-C',str(host),'add','products/default','features/classicalliterature/classicpoem/src/main/ets'],check=True)
subprocess.run(['git','-C',str(host),'commit','-m',f'test({case}): add on-device business-path measurement for {variant}'],check=True)
out=root/'device-tests/patches'/case;out.mkdir(parents=True,exist_ok=True)
(out/f'{variant}.patch').write_bytes(subprocess.check_output(['git','-C',str(host),'diff','HEAD~1','HEAD']))
