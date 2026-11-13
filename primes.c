#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int main(void){
    long n;
    if(scanf("%ld",&n)!=1) return 0;
    if(n<2){ printf("0\n"); return 0; }
    long half=(n>>1)+1;
    unsigned char *c=(unsigned char*)calloc((size_t)half,1);
    if(!c) return 1;
    for(long i=3;i*i<=n;i+=2){
        if(!c[i>>1]){
            long step=i<<1;
            for(long j=i*i;j<=n;j+=step) c[j>>1]=1;
        }
    }
    long cnt=1;
    for(long i=3;i<=n;i+=2) if(!c[i>>1]) cnt++;
    printf("%ld\n",cnt);
    free(c);
    return 0;
}
