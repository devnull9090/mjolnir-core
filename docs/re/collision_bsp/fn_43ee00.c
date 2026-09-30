// FUN_18043ee00 at 18043ee00 (rva 0x43ee00)

/* WARNING: Removing unreachable block (ram,0x00018043f12b) */

ulonglong FUN_18043ee00(undefined8 param_1,undefined8 param_2,int *param_3,undefined8 param_4,
                       undefined8 *param_5,longlong *param_6)

{
  void *_Src;
  uint uVar1;
  void *_Dst;
  byte bVar2;
  char cVar3;
  char cVar4;
  uint uVar5;
  longlong *plVar6;
  longlong lVar7;
  ulonglong uVar8;
  int *piVar9;
  longlong *plVar10;
  longlong *plVar11;
  undefined8 uVar12;
  undefined8 *puVar13;
  ulonglong uVar14;
  int iVar15;
  bool bVar16;
  int local_res18;
  uint local_res1c;
  longlong *local_208;
  undefined1 local_200 [8];
  undefined1 local_1f8;
  undefined8 *local_1c0;
  longlong local_1b8;
  undefined8 local_1b0;
  void *local_1a8;
  undefined4 local_1a0;
  undefined8 local_19c;
  undefined4 local_194;
  longlong local_190;
  undefined4 local_188;
  undefined8 local_180;
  undefined1 local_178;
  undefined2 local_176;
  undefined4 *local_70;
  undefined8 local_68;
  
  plVar6 = (longlong *)FUN_180441f00(param_5);
  if (plVar6 == (longlong *)0x0) {
    return 1;
  }
  bVar2 = *(byte *)(*(longlong *)
                     ((&DAT_182c2ccc0)[(uint)param_3[2] >> 0x1c] + 0x20 +
                     (ulonglong)(uint)param_3[2] * 4) + 0xa4) & 1;
  local_res18 = *param_3;
  local_res1c = bVar2 ^ 1;
  cVar3 = (**(code **)(*plVar6 + 0x80))(plVar6,&local_res18,8,1,0);
  cVar4 = '\0';
  if (cVar3 == '\0') goto LAB_18043f1f0;
  cVar4 = (**(code **)(*param_6 + 0x50))
                    (param_6,(&DAT_182c2ccc0)[(uint)param_3[2] >> 0x1c] +
                             (ulonglong)(uint)param_3[2] * 4);
  uVar1 = param_3[2];
  if (cVar4 == '\0') {
    lVar7 = *(longlong *)((&DAT_182c2ccc0)[uVar1 >> 0x1c] + 0x20 + (ulonglong)uVar1 * 4);
    cVar4 = (**(code **)(*plVar6 + 0x80))
                      (plVar6,(&DAT_182c2ccc0)[(uint)param_3[1] >> 0x1c] +
                              (ulonglong)(uint)param_3[1] * 4,(longlong)*(int *)(lVar7 + 0x28),
                       (longlong)*param_3,lVar7 + 0x80);
    goto LAB_18043f1f0;
  }
  cVar4 = '\x01';
  uVar1 = *(uint *)(*(longlong *)((&DAT_182c2ccc0)[uVar1 >> 0x1c] + 0x20 + (ulonglong)uVar1 * 4) +
                   0x28);
  uVar5 = DAT_1811511c0;
  if (DAT_1811511c0 < uVar1) {
    uVar5 = uVar1;
  }
  uVar8 = (ulonglong)uVar5;
  uVar14 = param_6[2];
  if (uVar14 == 0) {
LAB_18043ef75:
    puVar13 = (undefined8 *)(**(code **)(*param_6 + 0x20))(param_6);
    lVar7 = (**(code **)*puVar13)(puVar13,uVar8);
    if ((uVar5 != 0) && (lVar7 == 0)) {
      FUN_180043090();
    }
    param_6[1] = lVar7;
    param_6[2] = uVar8;
    uVar14 = uVar8;
    if (uVar5 != 0) goto LAB_18043efba;
  }
  else {
    if (uVar14 < uVar8) {
      plVar11 = (longlong *)(**(code **)(*param_6 + 0x20))(param_6);
      (**(code **)(*plVar11 + 8))(plVar11,param_6[1]);
      param_6[1] = 0;
      param_6[2] = 0;
      goto LAB_18043ef75;
    }
LAB_18043efba:
    memset((void *)param_6[1],0,uVar14);
  }
  lVar7 = *(longlong *)
           ((&DAT_182c2ccc0)[(uint)param_3[2] >> 0x1c] + 0x20 + (ulonglong)(uint)param_3[2] * 4);
  uVar1 = *(uint *)(lVar7 + 0x28);
  uVar8 = (ulonglong)(int)uVar1;
  local_res18 = 0;
  uVar14 = uVar8;
  if (0 < *param_3) {
    do {
      iVar15 = local_res18;
      bVar16 = cVar4 == '\0';
      cVar4 = '\0';
      if (bVar16) break;
      _Dst = (void *)param_6[1];
      if ((int)uVar14 != 0) {
        if (_Dst == (void *)0x0) {
          piVar9 = _errno();
          *piVar9 = 0x16;
          _invalid_parameter_noinfo();
        }
        else {
          _Src = (void *)((longlong)
                          *(int *)(*(longlong *)
                                    ((&DAT_182c2ccc0)[(uint)param_3[2] >> 0x1c] + 0x20 +
                                    (ulonglong)(uint)param_3[2] * 4) + 0x28) * (longlong)local_res18
                          + (&DAT_182c2ccc0)[(uint)param_3[1] >> 0x1c] +
                         (ulonglong)(uint)param_3[1] * 4);
          uVar14 = param_6[2];
          if ((_Src == (void *)0x0) || (uVar14 < uVar8)) {
            memset(_Dst,0,uVar14);
            if (_Src == (void *)0x0) {
              piVar9 = _errno();
              *piVar9 = 0x16;
            }
            else {
              iVar15 = local_res18;
              if (uVar8 <= uVar14) goto LAB_18043f0d2;
              piVar9 = _errno();
              *piVar9 = 0x22;
            }
            _invalid_parameter_noinfo();
            iVar15 = local_res18;
          }
          else {
            memcpy(_Dst,_Src,uVar8);
            iVar15 = local_res18;
          }
        }
      }
LAB_18043f0d2:
      plVar11 = (longlong *)(**(code **)(*param_6 + 0x10))(param_6);
      local_1b8 = *(longlong *)
                   ((&DAT_182c2ccc0)[(uint)param_3[2] >> 0x1c] + 0x20 +
                   (ulonglong)(uint)param_3[2] * 4);
      local_1b0 = *(undefined8 *)(local_1b8 + 0x20);
      local_1a0 = 0;
      local_188 = 0;
      local_176 = 0;
      local_180 = 0;
      local_178 = 0;
      local_194 = 0;
      local_19c = 0;
      local_190 = (longlong)*(int *)(local_1b8 + 0x28);
      local_1a8 = _Dst;
      (**(code **)(*plVar11 + 0x10))(plVar11,&local_1b8);
      cVar4 = FUN_180296230(&local_1b8);
      while (cVar4 != '\0') {
        plVar10 = (longlong *)(**(code **)*plVar11)(plVar11,*local_70,*(undefined8 *)(local_70 + 4))
        ;
        (**(code **)(*plVar10 + 0x20))(plVar10,local_68,*(undefined8 *)(local_70 + 4),param_6);
        cVar4 = FUN_180296230(&local_1b8);
      }
      cVar4 = (**(code **)(*plVar6 + 0x50))(plVar6);
      if (cVar4 != '\0') {
        FUN_18033e170(lVar7 + 0x80,_Dst,1);
      }
      cVar4 = (**(code **)(*plVar6 + 0x10))(plVar6,_Dst,uVar8);
      local_res18 = iVar15 + 1;
      uVar14 = (ulonglong)uVar1;
    } while (local_res18 < *param_3);
  }
LAB_18043f1f0:
  if (bVar2 != 0) {
    plVar11 = (longlong *)(**(code **)(*param_6 + 0x10))(param_6);
    uVar12 = (**(code **)(*plVar11 + 0x18))
                       (plVar11,(&DAT_182c2ccc0)[(uint)param_3[2] >> 0x1c] +
                                (ulonglong)(uint)param_3[2] * 4);
    puVar13 = (undefined8 *)(**(code **)(*plVar11 + 8))(plVar11,uVar12);
    local_1f8 = 1;
    local_1c0 = (undefined8 *)0x0;
    local_208 = plVar6;
    (**(code **)(*plVar6 + 0x40))(plVar6,local_200);
    iVar15 = 0;
    if (0 < *param_3) {
      do {
        bVar16 = cVar4 == '\0';
        cVar4 = '\0';
        if (bVar16) break;
        lVar7 = (longlong)
                *(int *)(*(longlong *)
                          ((&DAT_182c2ccc0)[(uint)param_3[2] >> 0x1c] + 0x20 +
                          (ulonglong)(uint)param_3[2] * 4) + 0x28) * (longlong)iVar15 +
                (&DAT_182c2ccc0)[(uint)param_3[1] >> 0x1c] + (ulonglong)(uint)param_3[1] * 4;
        cVar4 = (**(code **)*puVar13)(puVar13,lVar7,lVar7,uVar12,&local_208,param_6);
        iVar15 = iVar15 + 1;
      } while (iVar15 < *param_3);
    }
    if (local_1c0 != (undefined8 *)0x0) {
      (**(code **)*local_1c0)(local_1c0,0);
    }
  }
  if (cVar4 == '\0') {
    (*(code *)**(undefined8 **)param_5[9])((undefined8 *)param_5[9],0);
    param_5[9] = 0;
    *(undefined1 *)(param_5 + 2) = 1;
    uVar14 = (**(code **)(*(longlong *)*param_5 + 0x38))((longlong *)*param_5,param_5[1]);
    uVar14 = uVar14 & 0xffffffffffffff00;
  }
  else {
    uVar14 = FUN_180441f70(param_5,0x7467626c,0,plVar6);
  }
  return uVar14;
}


