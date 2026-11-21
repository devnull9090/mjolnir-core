/* Included after warfare_snapshot/adapter helpers. No UObject/world scans,
 * file IO or allocation on the simulation thread. Only read native tables. */
#ifndef MJOLNIR_WARFARE_MAP_H
#define MJOLNIR_WARFARE_MAP_H
#include "warfare_map_core.h"
static SRWLOCK warfare_tactical_lock=SRWLOCK_INIT;
static wmap_snapshot warfare_tactical_published;
static uint64_t warfare_tactical_instance,warfare_tactical_sample_ms;

static void warfare_tactical_publish(const wmap_snapshot *s) {
    AcquireSRWLockExclusive(&warfare_tactical_lock);warfare_tactical_published=*s;
    ReleaseSRWLockExclusive(&warfare_tactical_lock);
}
static void warfare_tactical_clear(void) {
    wmap_snapshot empty;memset(&empty,0,sizeof empty);empty.status=1;
    empty.team=empty.local_index=empty.local_user=-1;empty.layout=WARFARE_LAYOUT_REVISION;
    warfare_tactical_publish(&empty);
    /* Throttle state belongs to the simulation thread; clear can also be
     * called by the Lua close path, so it never writes those two counters. */
}
static unsigned char *warfare_tactical_object(unsigned char *tls,uint32_t handle,unsigned *size,unsigned *type) {
    if (handle==WMAP_NONE || !(handle>>16)) return NULL;
    unsigned char *table=*(unsigned char **)(tls+0x20);
    unsigned char *slot=fd_slot(table,handle&0xffff,0x18,4096);
    /* On a replicated client +0x0c can name the host index; matching the
     * local index is NOT valid. Salt, occupancy and bounded index still are.
     * See blam-live/world.rs objects() and its two-PC verified comment. */
    if (!slot || *(uint16_t *)slot!=(uint16_t)(handle>>16)
        || *(uint16_t *)(slot+0x0c)>=*(unsigned *)(table+0x2c)
        || *(uint16_t *)(slot+6)<0x80 || *(uint16_t *)(slot+4)>13) return NULL;
    *size=*(uint16_t *)(slot+6);*type=*(uint16_t *)(slot+4);
    return *(unsigned char **)(slot+0x10);
}
static int warfare_tactical_kind(uint32_t tag) {
    const char *name=warfare_tag_name(tag);
    if (!name) return -1;
    if (!_stricmp(name,"objects\\vehicles\\human\\warthog\\warthog")) return WM_HOG;
    if (!_stricmp(name,"objects\\vehicles\\human\\scorpion\\scorpion")) return WM_TANK;
    if (!_stricmp(name,"objects\\vehicles\\covenant\\banshee\\banshee")) return WM_BANSHEE;
    if (!_stricmp(name,"objects\\mjolnir\\warfare\\pelican\\pwr_pelican")) return WM_PELICAN;
    return -1;
}
static int warfare_tactical_lookup(void *context,uint32_t handle,wmap_object *out) {
    unsigned size=0,type=0;unsigned char *object=warfare_tactical_object((unsigned char *)context,handle,&size,&type);
    if (!object) return 0;
    memset(out,0,sizeof *out);out->handle=handle;out->type=(int)type;out->kind=-1;out->team=-1;
    out->parent=*(uint32_t *)(object+0x14);out->first_child=*(uint32_t *)(object+0x10);out->next=*(uint32_t *)(object+0x0c);
    for (int k=0;k<3;k++) {out->position[k]=((float *)(object+0x44))[k]*WARFARE_METRES_PER_WU;out->forward[k]=((float *)(object+0x50))[k];}
    if (type==1) out->kind=warfare_tactical_kind(*(uint32_t *)object);
    /* Native object_get_health reads damage section0. Never read a guessed
     * health float, or past the header's validated datum allocation. */
    if (size>=0x178) {
        unsigned bytes=*(uint16_t *)(object+0x174),offset=*(uint16_t *)(object+0x176);
        if (bytes>=0x18 && offset>=0x178 && offset<=size && bytes<=size-offset
            && *(uint16_t *)(object+offset+0x0e)!=UINT16_MAX) {
            float health=*(float *)(object+offset+0x10);
            out->alive=isfinite(health) && health>0;
        }
    }
    return 1;
}
static void warfare_tactical_collect(unsigned char *tls,const warfare_snapshot *s) {
    wmap_input input;memset(&input,0,sizeof input);
    input.instance=s->instance;input.sampled_ms=s->sampled_ms;input.tick=s->tick;input.phase=s->globals[0];
    input.score[0]=s->globals[7];input.score[1]=s->globals[8];
    for (int i=0;i<3;i++) input.owners[i]=s->globals[9+i]&3; /* low bits: owner (SiteState) */
    input.known_carriers[0]=s->host ? warfare.carrier[0] : WMAP_NONE;
    input.known_carriers[1]=s->host ? warfare.carrier[1] : WMAP_NONE;
    unsigned char *players=*(unsigned char **)(tls+0x30),*users=*(unsigned char **)(tls+0x118);
    for (int i=0;i<WMAP_PLAYERS;i++) {
        wmap_player *p=&input.players[i];p->unit=WMAP_NONE;p->team=p->local_user=-1;
        unsigned char *player=fd_slot(players,(unsigned)i,0x4b0,WMAP_PLAYERS);
        if (!player || !*(uint16_t *)player) continue;
        p->present=1;p->id=(uint32_t)*(uint16_t *)player<<16 | (unsigned)i;
        p->unit=*(uint32_t *)(player+0x28);p->team=(signed char)player[0xad];
        int local=users ? *(int *)(users+0x34+i*4) : -1;
        p->local_user=local>=0 && local<=1 ? local : -1;
    }
    unsigned char *table=*(unsigned char **)(tls+0x20);
    unsigned count=table ? *(unsigned *)(table+0x44) : 0;
    if (!table || count>4096) {warfare_tactical_clear();return;}
    for (unsigned i=0;i<count;i++) {
        unsigned char *slot=fd_slot(table,i,0x18,4096);
        if (!slot || *(uint16_t *)(slot+4)!=1) continue;
        uint32_t handle=(uint32_t)*(uint16_t *)slot<<16 | i;
        wmap_object object;
        if (!warfare_tactical_lookup(tls,handle,&object) || object.kind<WM_HOG || object.kind>WM_PELICAN
            || object.parent!=WMAP_NONE || !object.alive) continue;
        if (input.vehicle_count==WMAP_VEHICLES) {warfare_tactical_clear();return;}
        input.vehicles[input.vehicle_count++]=handle;
    }
    wmap_snapshot result;wmap_build(&input,warfare_tactical_lookup,tls,&result);warfare_tactical_publish(&result);
}
static void warfare_tactical_tick(unsigned char *tls,const warfare_snapshot *s) {
    if (!tls || !s || !s->ready || !s->instance) {warfare_tactical_clear();return;}
    if (s->instance==warfare_tactical_instance && s->sampled_ms>=warfare_tactical_sample_ms
        && s->sampled_ms-warfare_tactical_sample_ms<200) return;
    warfare_tactical_instance=s->instance;warfare_tactical_sample_ms=s->sampled_ms;
    __try {warfare_tactical_collect(tls,s);}
    __except(EXCEPTION_EXECUTE_HANDLER) {warfare_tactical_clear();}
}
static void warfare_tactical_pump(const char *directory) {
    static uint64_t last_write;
    uint64_t now=GetTickCount64();
    if (last_write && now>=last_write && now-last_write<180) return;
    last_write=now;
    wmap_snapshot s;AcquireSRWLockShared(&warfare_tactical_lock);s=warfare_tactical_published;
    ReleaseSRWLockShared(&warfare_tactical_lock);
    if (s.ready && (now<s.sampled_ms || now-s.sampled_ms>1000)) {s.ready=0;s.status=-5;s.count=0;}
    char path[MAX_PATH],temporary[MAX_PATH];
    int n=snprintf(path,sizeof path,"%swarfare_map.txt",directory);
    int m=snprintf(temporary,sizeof temporary,"%swarfare_map.tmp",directory);
    if (n<0 || n>=(int)sizeof path || m<0 || m>=(int)sizeof temporary) return;
    FILE *file=fopen(temporary,"w");if (!file) return;
    fprintf(file,"warfare-map 1\nready %d\nstatus %d\ninstance %llu\ntick %d\nsampled_ms %llu\nlayout %d\nteam %d\nlocal_index %d\nlocal_user %d\nphase %d\nscore %d %d\nbounds -1000 -1000 1000 1000\n",
        s.ready,s.status,(unsigned long long)s.instance,s.tick,(unsigned long long)s.sampled_ms,s.layout,s.team,s.local_index,s.local_user,s.phase,s.score[0],s.score[1]);
    static const char *kind[]={"self","player","hog","tank","banshee","pelican","base","capture"};
    for (int i=0;i<s.count;i++) {const wmap_marker *v=&s.markers[i];
        fprintf(file,"marker %s %u %d %.3f %.3f %.3f\n",kind[v->kind],v->id,v->team,v->x,v->y,v->heading);
    }
    fprintf(file,"end %d\n",s.count);
    int failed=ferror(file);if (fclose(file)) failed=1;
    if (!failed) MoveFileExA(temporary,path,MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH);
}
#endif
