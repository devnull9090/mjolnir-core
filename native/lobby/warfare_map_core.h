/* Read-only tactical map policy. Portable, bounded, no engine/global state. */
#ifndef MJOLNIR_WARFARE_MAP_CORE_H
#define MJOLNIR_WARFARE_MAP_CORE_H
#include <math.h>
#include <stdint.h>
#include <string.h>
#include "warfare_layout.h"

#define WMAP_NONE UINT32_MAX
#define WMAP_PLAYERS 16
#define WMAP_VEHICLES 32
#define WMAP_MARKERS 64
#define WMAP_CHILDREN 64
enum wmap_kind { WM_SELF, WM_PLAYER, WM_HOG, WM_TANK, WM_BANSHEE, WM_PELICAN, WM_BASE, WM_CAPTURE };
typedef struct {
    uint32_t handle, parent, first_child, next;
    int type, kind, team, alive;
    float position[3], forward[3]; /* authoring metres, +X east/+Y north */
} wmap_object;
typedef struct { uint32_t id, unit; int present, team, local_user; } wmap_player;
typedef struct { int kind, team; uint32_t id; float x, y, heading; } wmap_marker;
typedef struct {
    int ready, status, tick, layout, team, local_index, local_user, phase, score[2], count;
    uint64_t instance, sampled_ms;
    wmap_marker markers[WMAP_MARKERS];
} wmap_snapshot;
typedef struct {
    uint64_t instance, sampled_ms;
    int tick, phase, score[2], owners[3], vehicle_count;
    /* Each site's chosen candidate (blam-megalo SiteState.candidate). */
    int candidates[3];
    wmap_player players[WMAP_PLAYERS];
    uint32_t vehicles[WMAP_VEHICLES], known_carriers[2];
} wmap_input;
typedef int (*wmap_lookup)(void *, uint32_t, wmap_object *);

static int wmap_pose(const wmap_object *o) {
    if (!o || o->handle==WMAP_NONE || !(o->handle>>16)) return 0;
    for (int k=0;k<3;k++)
        if (!isfinite(o->position[k]) || !isfinite(o->forward[k])
            || o->position[k]<warfare_scenario_min[k] || o->position[k]>warfare_scenario_max[k]
            || fabsf(o->forward[k])>1.1f) return 0;
    return 1;
}
static int wmap_add(wmap_snapshot *out,int kind,uint32_t id,int team,const wmap_object *o) {
    if (out->count>=WMAP_MARKERS || kind<WM_SELF || kind>WM_CAPTURE || team< -1 || team>1 || !wmap_pose(o)) return 0;
    wmap_marker *m=&out->markers[out->count++];
    m->kind=kind;m->id=id;m->team=team;m->x=o->position[0];m->y=o->position[1];
    float length=o->forward[0]*o->forward[0]+o->forward[1]*o->forward[1];
    m->heading=length>1e-8f ? atan2f(o->forward[1],o->forward[0])*57.29577951308232f : 0;
    return 1;
}
static int wmap_team(const wmap_input *in,const wmap_object *unit) {
    /* Player configuration is authoritative; a stale unit team byte cannot
     * turn an enemy into a teammate. Unknown/non-player allegiance is hidden. */
    for (int i=0;i<WMAP_PLAYERS;i++)
        if (in->players[i].present && in->players[i].unit==unit->handle) return in->players[i].team;
    return -1;
}
static int wmap_occupants(const wmap_input *in,const wmap_object *vehicle,int team,
                         wmap_lookup lookup,void *context,int *occupied) {
    uint32_t child=vehicle->first_child, seen[WMAP_CHILDREN];int n=0;
    *occupied=0;
    while (child!=WMAP_NONE) {
        if (n>=WMAP_CHILDREN) return 0;
        for (int i=0;i<n;i++) if (seen[i]==child) return 0;
        seen[n++]=child;
        wmap_object unit;
        if (!lookup(context,child,&unit) || unit.handle!=child || unit.parent!=vehicle->handle) return 0;
        if (unit.type==0 || unit.type==11 || unit.type==12) {
            /* Any hostile/unknown occupant hides the vehicle, even alongside
             * a friendly player. Corpse seats are conservatively occupied. */
            if (wmap_team(in,&unit)!=team) return 0;
            *occupied=1;
        }
        child=unit.next;
    }
    /* Independent player-parent check catches an incomplete replicated child
     * chain before it could expose an enemy occupied vehicle as neutral. */
    for (int i=0;i<WMAP_PLAYERS;i++) {
        const wmap_player *p=&in->players[i];wmap_object unit;
        if (!p->present || p->unit==WMAP_NONE) continue;
        if (!lookup(context,p->unit,&unit)) continue;
        if (unit.parent==vehicle->handle) {
            if (p->team!=team) return 0;
            *occupied=1;
        }
    }
    return 1;
}
static void wmap_build(const wmap_input *in,wmap_lookup lookup,void *context,wmap_snapshot *out) {
    memset(out,0,sizeof *out);out->status=-3;out->team=out->local_index=out->local_user=-1;
    out->layout=WARFARE_LAYOUT_REVISION;
    if (!in || !lookup || !in->instance || in->tick<0 || in->phase<0 || in->phase>3
        || in->vehicle_count<0 || in->vehicle_count>WMAP_VEHICLES) return;
    out->instance=in->instance;out->sampled_ms=in->sampled_ms;out->tick=in->tick;out->phase=in->phase;
    if (in->score[0]<0 || in->score[1]<0 || in->score[0]>32767 || in->score[1]>32767) return;
    for (int i=0;i<3;i++) if (in->owners[i]<0 || in->owners[i]>2) return;
    out->score[0]=in->score[0];out->score[1]=in->score[1];
    /* Only the primary local viewpoint is exported. Death retains its team;
     * missing/unassigned local players never fall back to a remote viewpoint. */
    for (int user=0;user<2 && out->local_index<0;user++) {
        for (int i=0;i<WMAP_PLAYERS;i++) if (in->players[i].present && in->players[i].local_user==user) {
            if (out->local_index>=0) {out->status=-2;out->local_index=-1;return;}
            out->local_index=i;out->local_user=user;
        }
    }
    if (out->local_index<0) {out->status=-2;return;}
    out->team=in->players[out->local_index].team;
    if (out->team<0 || out->team>1) {out->team=-1;out->status=-2;return;}
    for (int i=0;i<WMAP_PLAYERS;i++) {
        const wmap_player *p=&in->players[i];wmap_object unit,pose;
        if (!p->present || p->team!=out->team || !(p->id>>16)
            || !lookup(context,p->unit,&unit) || unit.handle!=p->unit || unit.type!=0 || !unit.alive) continue;
        pose=unit;
        if (unit.parent!=WMAP_NONE) {
            if (!lookup(context,unit.parent,&pose) || pose.handle!=unit.parent || pose.type!=1
                || pose.parent!=WMAP_NONE || !pose.alive) continue;
        }
        wmap_add(out,i==out->local_index ? WM_SELF : WM_PLAYER,p->id,p->team,&pose);
    }
    for (int i=0;i<in->vehicle_count;i++) {
        wmap_object vehicle;int occupied=0;
        if (!lookup(context,in->vehicles[i],&vehicle) || vehicle.handle!=in->vehicles[i]
            || vehicle.type!=1 || vehicle.kind<WM_HOG || vehicle.kind>WM_PELICAN
            || !vehicle.alive || vehicle.parent!=WMAP_NONE || !wmap_pose(&vehicle)) continue;
        if (!wmap_occupants(in,&vehicle,out->team,lookup,context,&occupied)) continue;
        if (vehicle.kind==WM_PELICAN) {
            /* Known host carrier identities are explicit; on a client hide
             * an empty unbound Pelican until a friendly occupant proves it. */
            if (vehicle.handle==in->known_carriers[1-out->team]
                || (!occupied && vehicle.handle!=in->known_carriers[out->team])) continue;
        }
        wmap_add(out,vehicle.kind,vehicle.handle,occupied || vehicle.kind==WM_PELICAN ? out->team : -1,&vehicle);
    }
    for (int i=0;i<5;i++) {
        wmap_object fixed;memset(&fixed,0,sizeof fixed);fixed.handle=0x10000;fixed.forward[0]=1;
        if (i<2) memcpy(fixed.position,warfare_layout_markers[4+i],sizeof fixed.position);
        else {
            /* The site where this match put it; an unknown candidate draws the classic spot. */
            int site=i-2,c=in->candidates[site];
            if (c<0 || c>=warfare_candidate_counts[site]) c=0;
            memcpy(fixed.position,warfare_candidates[site][c],sizeof fixed.position);
        }
        int team=i<2 ? i : in->owners[i-2]==1 ? 0 : in->owners[i-2]==2 ? 1 : -1;
        wmap_add(out,i<2 ? WM_BASE : WM_CAPTURE,(uint32_t)(i<2 ? i : i-2),team,&fixed);
    }
    out->ready=1;out->status=2;
}

#endif
