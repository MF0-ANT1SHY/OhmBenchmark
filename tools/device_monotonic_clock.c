/* Read-only evaluator clock; never linked into the application. */
#include <time.h>
#include <stdint.h>
#include <inttypes.h>
#include <stdio.h>
int main(void){
 struct timespec t;if(clock_gettime(CLOCK_MONOTONIC,&t))return 1;
 if(t.tv_sec<0||t.tv_nsec<0||t.tv_nsec>=1000000000)return 2;
 uint64_t ns=(uint64_t)t.tv_sec*1000000000u+(uint64_t)t.tv_nsec;
 printf("{\"clock\":\"CLOCK_MONOTONIC\",\"ns\":%" PRIu64 "}\n",ns);return 0;
}
