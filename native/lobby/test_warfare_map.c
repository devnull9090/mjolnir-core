#include <assert.h>
#include <stdio.h>
#include "warfare_map_core.h"

typedef struct { wmap_object objects[128];int count,calls; } fixture;
static int lookup(void *context,uint32_t handle,wmap_object *out) {
    fixture *f=(fixture *)context;f->calls++;
    for (int i=0;i<f->count;i++) if (f->objects[i].handle==handle) {*out=f->objects[i];return 1;}
    return 0;
}
static wmap_object *object(fixture *f,int type,int kind,float x,float y) {
    assert(f->count<128);wmap_object *o=&f->objects[f->count];memset(o,0,sizeof *o);
    o->handle=0x10000u+(unsigned)f->count++;o->parent=o->first_child=o->next=WMAP_NONE;
    o->type=type;o->kind=kind;o->alive=1;o->team=-1;o->position[0]=x;o->position[1]=y;o->position[2]=110;o->forward[0]=1;return o;
}
static wmap_object *player(fixture *f,wmap_input *in,int slot,int team,int user,float x) {
    wmap_object *o=object(f,0,-1,x,0);wmap_player *p=&in->players[slot];
    p->present=1;p->id=0x90000u+(unsigned)slot;p->unit=o->handle;p->team=team;p->local_user=user;return o;
}
static wmap_object *vehicle(fixture *f,wmap_input *in,int kind) {
    wmap_object *o=object(f,1,kind,-20,30);assert(in->vehicle_count<WMAP_VEHICLES);
    in->vehicles[in->vehicle_count++]=o->handle;return o;
}
static void setup(fixture *f,wmap_input *in) {
    memset(f,0,sizeof *f);memset(in,0,sizeof *in);in->instance=1234567890123456ull;in->sampled_ms=500;in->tick=30;in->phase=2;
    in->known_carriers[0]=in->known_carriers[1]=WMAP_NONE;
    for (int i=0;i<WMAP_PLAYERS;i++) {in->players[i].unit=WMAP_NONE;in->players[i].local_user=-1;in->players[i].team=-1;}
    player(f,in,0,0,0,11);player(f,in,1,1,-1,777);player(f,in,2,0,-1,55);
}
static const wmap_marker *marker(const wmap_snapshot *s,int kind,uint32_t id) {
    for (int i=0;i<s->count;i++) if (s->markers[i].kind==kind && s->markers[i].id==id) return &s->markers[i];
    return NULL;
}
static void test_team_public_and_heading(void) {
    fixture f;wmap_input in;wmap_snapshot out;setup(&f,&in);in.owners[0]=0;in.owners[1]=1;in.owners[2]=2;
    f.objects[0].forward[0]=0;f.objects[0].forward[1]=1;
    wmap_object *hog=vehicle(&f,&in,WM_HOG);wmap_build(&in,lookup,&f,&out);
    assert(out.ready && out.status==2 && out.team==0 && out.local_index==0 && out.local_user==0 && out.count==8);
    assert(out.instance==in.instance && out.sampled_ms==in.sampled_ms);
    assert(marker(&out,WM_SELF,in.players[0].id)->heading==90);
    assert(marker(&out,WM_PLAYER,in.players[2].id));assert(!marker(&out,WM_PLAYER,in.players[1].id));
    assert(marker(&out,WM_HOG,hog->handle)->team==-1);
    assert(marker(&out,WM_BASE,0)->team==0 && marker(&out,WM_BASE,1)->team==1);
    assert(marker(&out,WM_CAPTURE,0)->team==-1 && marker(&out,WM_CAPTURE,1)->team==0 && marker(&out,WM_CAPTURE,2)->team==1);
    for (int i=0;i<out.count;i++) assert(out.markers[i].x!=777);
}
static void test_no_viewpoint_leak(void) {
    fixture f;wmap_input in;wmap_snapshot out;setup(&f,&in);in.players[0].local_user=-1;
    wmap_build(&in,lookup,&f,&out);assert(!out.ready && out.status==-2 && out.count==0);
    in.players[2].local_user=1;wmap_build(&in,lookup,&f,&out);assert(out.ready && out.local_index==2);
    in.players[0].local_user=0;in.players[0].team=-1;wmap_build(&in,lookup,&f,&out);
    assert(!out.ready && out.team==-1 && out.count==0); /* No fallback from unassigned primary. */
    in.players[0].team=0;in.players[2].local_user=0;wmap_build(&in,lookup,&f,&out);assert(!out.ready && out.count==0);
}
static void test_death_salts_finite_and_parent(void) {
    fixture f;wmap_input in;wmap_snapshot out;setup(&f,&in);
    f.objects[0].alive=0;wmap_build(&in,lookup,&f,&out);assert(out.ready && !marker(&out,WM_SELF,in.players[0].id));
    in.players[2].unit+=0x10000;wmap_build(&in,lookup,&f,&out);assert(!marker(&out,WM_PLAYER,in.players[2].id));
    in.players[2].unit-=0x10000;f.objects[2].position[0]=NAN;wmap_build(&in,lookup,&f,&out);assert(out.count==5);
    f.objects[2].position[0]=55;wmap_object *hog=vehicle(&f,&in,WM_HOG);
    f.objects[0].alive=1;f.objects[0].parent=hog->handle;f.objects[0].position[0]=999;
    hog->first_child=f.objects[0].handle;hog->forward[0]=-1;
    wmap_build(&in,lookup,&f,&out);assert(marker(&out,WM_SELF,in.players[0].id)->x==hog->position[0]);
    assert(fabsf(marker(&out,WM_SELF,in.players[0].id)->heading)==180);
    assert(marker(&out,WM_HOG,hog->handle)->team==0);
    hog->position[2]=651;wmap_build(&in,lookup,&f,&out);assert(!marker(&out,WM_SELF,in.players[0].id) && !marker(&out,WM_HOG,hog->handle));
}
static void test_enemy_unknown_and_incomplete_chain(void) {
    fixture f;wmap_input in;wmap_snapshot out;setup(&f,&in);wmap_object *tank=vehicle(&f,&in,WM_TANK);
    tank->first_child=f.objects[1].handle;f.objects[1].parent=tank->handle;
    wmap_build(&in,lookup,&f,&out);assert(!marker(&out,WM_TANK,tank->handle));
    /* An incomplete child chain cannot classify a known enemy rider as neutral. */
    tank->first_child=WMAP_NONE;wmap_build(&in,lookup,&f,&out);assert(!marker(&out,WM_TANK,tank->handle));
    f.objects[1].parent=WMAP_NONE;wmap_object *unknown=object(&f,0,-1,0,0);
    unknown->parent=tank->handle;tank->first_child=unknown->handle;unknown->team=0;
    wmap_build(&in,lookup,&f,&out);assert(!marker(&out,WM_TANK,tank->handle)); /* No guessed AI ownership. */
    tank->first_child=f.objects[0].handle;f.objects[0].parent=tank->handle;f.objects[0].next=f.objects[1].handle;f.objects[1].parent=tank->handle;
    wmap_build(&in,lookup,&f,&out);assert(!marker(&out,WM_TANK,tank->handle)); /* Mixed seat teams hide. */
}
static void test_child_bounds_cycles_and_turrets(void) {
    fixture f;wmap_input in;wmap_snapshot out;setup(&f,&in);wmap_object *hog=vehicle(&f,&in,WM_HOG);
    wmap_object *weapon=object(&f,2,-1,0,0);weapon->parent=hog->handle;hog->first_child=weapon->handle;
    wmap_build(&in,lookup,&f,&out);assert(marker(&out,WM_HOG,hog->handle)->team==-1);
    weapon->next=weapon->handle;wmap_build(&in,lookup,&f,&out);assert(!marker(&out,WM_HOG,hog->handle));
    weapon->next=0xdeadbeef;wmap_build(&in,lookup,&f,&out);assert(!marker(&out,WM_HOG,hog->handle));
    weapon->next=WMAP_NONE;weapon->parent=WMAP_NONE;wmap_build(&in,lookup,&f,&out);assert(!marker(&out,WM_HOG,hog->handle));
    weapon->parent=hog->handle;wmap_object *tail=weapon;
    for (int i=0;i<WMAP_CHILDREN;i++) {wmap_object *next=object(&f,2,-1,0,0);next->parent=hog->handle;tail->next=next->handle;tail=next;}
    wmap_build(&in,lookup,&f,&out);assert(!marker(&out,WM_HOG,hog->handle));
}
static void test_pelican_and_capacity(void) {
    fixture f;wmap_input in;wmap_snapshot out;setup(&f,&in);wmap_object *p=vehicle(&f,&in,WM_PELICAN);
    wmap_build(&in,lookup,&f,&out);assert(!marker(&out,WM_PELICAN,p->handle));
    in.known_carriers[1]=p->handle;wmap_build(&in,lookup,&f,&out);assert(!marker(&out,WM_PELICAN,p->handle));
    in.known_carriers[1]=WMAP_NONE;in.known_carriers[0]=p->handle;
    wmap_build(&in,lookup,&f,&out);assert(marker(&out,WM_PELICAN,p->handle)->team==0);
    in.known_carriers[0]=WMAP_NONE;p->first_child=f.objects[0].handle;f.objects[0].parent=p->handle;
    wmap_build(&in,lookup,&f,&out);assert(marker(&out,WM_PELICAN,p->handle)->team==0);
    p->first_child=f.objects[1].handle;f.objects[1].parent=p->handle;
    wmap_build(&in,lookup,&f,&out);assert(!marker(&out,WM_PELICAN,p->handle));
    in.vehicle_count=WMAP_VEHICLES+1;wmap_build(&in,lookup,&f,&out);assert(!out.ready && out.count==0);
    setup(&f,&in);for (int i=3;i<WMAP_PLAYERS;i++) player(&f,&in,i,0,-1,(float)i);
    in.players[1].team=0;for (int i=0;i<WMAP_VEHICLES;i++) vehicle(&f,&in,WM_HOG);
    wmap_build(&in,lookup,&f,&out);assert(out.ready && out.count==WMAP_PLAYERS+WMAP_VEHICLES+5 && out.count<=WMAP_MARKERS);
}
static void test_invalid_mode_inputs(void) {
    fixture f;wmap_input in;wmap_snapshot out;setup(&f,&in);in.instance=0;wmap_build(&in,lookup,&f,&out);assert(!out.ready);
    setup(&f,&in);in.owners[1]=4;wmap_build(&in,lookup,&f,&out);assert(!out.ready && out.count==0);
    setup(&f,&in);in.owners[1]=3;wmap_build(&in,lookup,&f,&out);assert(out.ready); /* the Covenant hold B */
    setup(&f,&in);in.score[0]=-1;wmap_build(&in,lookup,&f,&out);assert(!out.ready && out.score[0]==0);
    setup(&f,&in);in.phase=4;wmap_build(&in,lookup,&f,&out);assert(!out.ready);
}
/* Moving zones: a site is drawn where this match put it; an unknown
 * candidate falls back to the classic spot rather than to a guess. */
static void test_capture_candidates(void) {
    fixture f;wmap_input in;wmap_snapshot out;setup(&f,&in);
    in.candidates[0]=2;in.candidates[1]=0;in.candidates[2]=99;
    wmap_build(&in,lookup,&f,&out);assert(out.ready);
    const wmap_marker *a=marker(&out,WM_CAPTURE,0),*b=marker(&out,WM_CAPTURE,1),*c=marker(&out,WM_CAPTURE,2);
    assert(a && fabsf(a->x-warfare_candidates[0][2][0])<0.01f && fabsf(a->y-warfare_candidates[0][2][1])<0.01f);
    assert(b && fabsf(b->x-warfare_candidates[1][0][0])<0.01f);
    assert(c && fabsf(c->x-warfare_candidates[2][0][0])<0.01f);
    assert(warfare_candidates[0][0][0]==warfare_layout_markers[7][0]); /* candidate 0 is the classic marker */
}
int main(void) {
    test_team_public_and_heading();test_no_viewpoint_leak();test_death_salts_finite_and_parent();
    test_enemy_unknown_and_incomplete_chain();test_child_bounds_cycles_and_turrets();test_pelican_and_capacity();test_invalid_mode_inputs();test_capture_candidates();
    puts("warfare tactical map: team/privacy, seats, corpse/salt/finite guards, bounded chains/capacity, parent poses and public objectives PASS");return 0;
}
