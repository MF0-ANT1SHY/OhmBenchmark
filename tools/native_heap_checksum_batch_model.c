/* Diagnostic bounded checkpoint search only; never validates or scores captures.
 * Compile: cc -O2 -Wno-deprecated-declarations native_heap_checksum_batch_model.c -lcrypto
 * Searches at most 22 records and 4 MiB; SHA256_Final intentionally mutates ctx.
 */
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <openssl/sha.h>
static unsigned char *blob;static long offsets[25];static int count,hits;static unsigned long leaves;
static void search(int index,SHA256_CTX ctx,unsigned mask){
 unsigned char hash[32];
 if(index==count){
  leaves++;
  for(int extra=1;extra<=4;extra++){
   SHA256_Final(hash,&ctx);
   if(!memcmp(hash,blob+24,32)){hits++;printf("MATCH mask=%u extra=%d\n",mask,extra);fflush(stdout);}
  }
  return;
 }
 SHA256_Update(&ctx,blob+offsets[index],offsets[index+1]-offsets[index]);
 search(index+1,ctx,mask);
 SHA256_Final(hash,&ctx);
 search(index+1,ctx,mask|(1u<<index));
}
int main(int argc,char**argv){
 if(argc!=2)return 2;FILE*f=fopen(argv[1],"rb");if(!f)return 3;
 fseek(f,0,SEEK_END);long size=ftell(f);rewind(f);if(size<1024||size>4*1024*1024)return 8;blob=malloc(size);if(!blob)return 4;
 if(fread(blob,1,size,f)!=(size_t)size)return 5;fclose(f);
 offsets[0]=1024;long off=1024;
 while(off<size){if(count>=22)return 7;uint32_t n;memcpy(&n,blob+off,4);if(!n||off+4+n>size)return 6;off+=n+4;offsets[++count]=off;}
 SHA256_CTX ctx;SHA256_Init(&ctx);search(0,ctx,0);
 printf("records=%d checkpoint_sequences=%lu matches=%d\n",count,leaves,hits);free(blob);return 0;
}
