import { common } from '@kit.AbilityKit';
import { relationalStore } from '@kit.ArkData';
import { AppStore } from '../state/AppStore';
import { NavigationTarget, ViewType } from '../model/Models';
import { FeedFilter } from '../model/Filter';
import { OhmProbe } from './OhmProbe';

export async function runSheafUiBench(context: common.UIAbilityContext, store: AppStore): Promise<void> {
  await OhmProbe.measure(context, 'sheafreader_article_list_foreach', async (): Promise<void> => {
    const db = await relationalStore.getRdbStore(context, {name:'sheaf_reader.db',securityLevel:relationalStore.SecurityLevel.S1});
    await db.executeSql('DELETE FROM articles'); await db.executeSql('DELETE FROM feeds');
    await db.executeSql("INSERT INTO feeds(id,url,title) VALUES (1,'https://example.org/feed','Engineering Feed')");
    await db.executeSql("WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM n WHERE x<1000) INSERT INTO articles(feed_id,title,guid,content,snippet) SELECT 1, 'Engineering article '||x, 'article-'||x, 'HarmonyOS rendering performance', 'Article list performance study' FROM n");
    if (store.sidebarOpen) await store.toggleSidebar();
    store.currentNav = new NavigationTarget(); store.filter = new FeedFilter(); store.searchQuery = '';
    store.articles = []; await store.switchView(ViewType.List);
    AppStorage.SetOrCreate('ohmArticleCount', 0);
    await new Promise<void>((resolve) => { setTimeout(resolve, 1000); });
  }, async (): Promise<number> => {
    const deadline = Date.now()+10000;
    await store.resetArticles();
    await store.loadMoreArticles();
    await new Promise<void>((resolve) => { setTimeout(resolve, Math.max(0,deadline-Date.now())); });
    return store.articles.length;
  });
}
