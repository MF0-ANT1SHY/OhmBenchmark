import { common } from '@kit.AbilityKit';
import { relationalStore } from '@kit.ArkData';
import { Artist } from '../common/entities/song/Song';
import { getArtists } from '../common/functions/common/convert';
import RelationalStoreUtils from '../common/utils/data/RelationalStoreUtils';
import { OhmProbe } from './OhmProbe';
export async function runCloudBench(context: common.UIAbilityContext,name: string): Promise<void> {
  if (name==='cloudmusic_local_song_memory_filter') {
    await RelationalStoreUtils.init();
    const db=await relationalStore.getRdbStore(context,{name:'LocalSongs.db',securityLevel:relationalStore.SecurityLevel.S1});
    await db.executeSql('DELETE FROM songs');
    await db.executeSql("WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM n WHERE x<1000) INSERT INTO songs(songId,name,artists,songFile,picFile,lyricFile) SELECT x,'Song '||x,'Artist','/music/song-'||printf('%05d',x)||'.flac','','' FROM n");
    AppStorage.SetOrCreate('ohmLocalBench',true);
    return;
  }
  const artists: Artist[]=[];
  for (let i=0;i<5;i++) artists.push({id:i,name:'Artist '+i});
  await OhmProbe.measure(context,name,async (): Promise<void> => {},async (): Promise<number> => {
    let count=0;
    for (let i=0;i<100000;i++) count+=getArtists(artists).length;
    return count;
  });
}
