import { common } from '@kit.AbilityKit';
import { relationalStore } from '@kit.ArkData';
import { OhmProbe } from './OhmProbe';
import { DatabaseManager } from '../data/DatabaseManager';
import { FeedService } from '../services/FeedService';
import { FeedParser } from './FeedParser';
import { Article } from '../model/Models';

export async function runSheafBench(context: common.UIAbilityContext, name: string): Promise<void> {
  let xml: string = '';
  const articles: Article[] = [];
  const db = DatabaseManager.getInstance();
  await OhmProbe.measure(context, name, async (): Promise<void> => {
    if (name === 'sheafreader_extract_tag_tolowercase') {
      const body = '<p>HarmonyOS Performance Engineering. ΑΝΑΛΥΣΗ ΔΕΔΟΜΕΝΩΝ; ПРИЛОЖЕНИЕ И ПРОИЗВОДИТЕЛЬНОСТЬ; İstanbul İŞLEM; 中文应用性能测试。</p>'.repeat(650);
      const items: string[] = [];
      for (let i = 0; i < 100; i++) {
        items.push('<item><title>Engineering Article ' + i + '</title><link>https://example.org/' + i + '</link><description>Article summary</description><pubDate>Wed, 30 Sep 2026 12:00:00 GMT</pubDate><guid>article-' + i + '</guid><author>Engineering Team</author><content:encoded><![CDATA[' + body + ']]></content:encoded></item>');
      }
      xml = '<rss version="2.0"><channel><title>Engineering Feed</title><link>https://example.org</link><description>Long form engineering articles</description>' + items.join('') + '</channel></rss>';
      return;
    }
    const store = await relationalStore.getRdbStore(context, {name:'sheaf_reader.db',securityLevel:relationalStore.SecurityLevel.S1});
    await store.executeSql('DELETE FROM articles');
    await store.executeSql('DELETE FROM feeds');
    if (name === 'sheafreader_refresh_feeds_sequential') {
      await store.executeSql("WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM n WHERE x<40) INSERT INTO feeds(id,url,title) SELECT x, 'http://127.0.0.1:18765/feed/'||x, 'Feed '||x FROM n");
      return;
    }
    await store.executeSql("WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM n WHERE x<200) INSERT INTO feeds(id,url,title) SELECT x, 'https://example.org/feed/'||x, 'Feed '||x FROM n");
    await store.executeSql("WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM n WHERE x<10000) INSERT INTO articles(feed_id,title,guid,content) SELECT ((x-1)%200)+1, 'Article '||x, 'article-'||x, 'Engineering article content' FROM n");
    if (name === 'sheafreader_insert_duplicate_exception') {
      for (let i=1;i<=10000;i++) {
        const a = new Article(); a.feedId=((i-1)%200)+1;
        a.guid='article-'+i; a.title='Article '+i; a.content='Engineering article content';
        articles.push(a);
      }
    }
  }, async (): Promise<number> => {
    if (name === 'sheafreader_refresh_feeds_sequential') {
      const outcome = await FeedService.getInstance().refreshAllFeeds((_done: number, _total: number): void => {});
      console.info('OHMB refresh inserted=' + outcome.inserted + ' failures=' + outcome.failures.length);
      const store = await relationalStore.getRdbStore(context, {name:'sheaf_reader.db',securityLevel:relationalStore.SecurityLevel.S1});
      const rs = await store.querySql('SELECT COUNT(*) AS n FROM articles');
      rs.goToFirstRow(); const count = rs.getLong(0); rs.close();
      return outcome.failures.length === 0 ? count : -outcome.failures.length;
    }
    if (name === 'sheafreader_extract_tag_tolowercase') {
      const parsed = FeedParser.parse(xml, 'https://example.org/feed');
      return parsed === null ? -1 : parsed.articles.length;
    }
    if (name === 'sheafreader_unread_counts_n_plus_1') {
      const feeds = await FeedService.getInstance().getFeedsWithCounts();
      let sum = 0; for (const f of feeds) sum += f.unreadCount;
      return sum;
    }
    let inserted = 0;
    for (const a of articles) { if (await db.insertArticle(a) > 0) inserted++; }
    return inserted;
  });
}
