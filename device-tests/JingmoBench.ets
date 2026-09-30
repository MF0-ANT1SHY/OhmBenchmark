import { common } from '@kit.AbilityKit';
import { OhmProbe } from './OhmProbe';
import DbUtil from 'utils/src/main/ets/database/DbUtil';
import { ClassicPoem, ClassicPoemDao } from 'classicalliterature_classicpoem';
import { DbTableConst } from 'constants';
// EXTRA_IMPORT

export async function runJingmoBench(context: common.UIAbilityContext, name: string): Promise<void> {
  const poems: ClassicPoem[] = [];
  const dao = new ClassicPoemDao();
  await OhmProbe.measure(context, name, async (): Promise<void> => {
    const store = DbUtil.objectiveRDB;
    if (!store) throw new Error('Database unavailable');
    await store.executeSql('DELETE FROM ' + DbTableConst.ClassicPoemTable);
    const columns = 'id,dynasty,writer,writer_introduction,title,subtitle,preface,content,annotation,translation,creative_background,explain,comment,collection,category';
    if (name !== 'jingmo_dataset_import_no_transaction') {
      await store.executeSql('WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM n WHERE x<50000) INSERT INTO ' + DbTableConst.ClassicPoemTable + '(' + columns + ") SELECT x,'唐','李白','','诗歌 '||x,'','','床前明月光，疑是地上霜。举头望明月，低头思故乡。','','','','','','唐诗','诗歌' FROM n");
    }
    if (name !== 'jingmo_random_poem_orderby_random') {
      const count = name === 'jingmo_dataset_import_no_transaction' ? 3000 : 50000;
      for (let i=1;i<=count;i++) {
        poems.push(new ClassicPoem(i,'唐','李白','','诗歌 '+i,'','','床前明月光，疑是地上霜。举头望明月，低头思故乡。','','','','','','唐诗','诗歌'));
      }
    }
  }, async (): Promise<number> => {
    // MEASURE_ACTION
  });
}
