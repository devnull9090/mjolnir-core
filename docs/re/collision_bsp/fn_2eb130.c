// FUN_1802eb130 at 1802eb130 (rva 0x2eb130)

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

undefined8
FUN_1802eb130(longlong param_1,uint param_2,int param_3,int param_4,undefined8 param_5,
             undefined1 (*param_6) [16])

{
  longlong lVar1;
  undefined4 uVar2;
  uint uVar3;
  longlong lVar4;
  undefined1 auVar5 [16];
  undefined1 auVar6 [16];
  char cVar7;
  int iVar8;
  undefined8 uVar9;
  int iVar10;
  ulonglong uVar11;
  longlong lVar12;
  undefined1 auVar13 [16];
  undefined1 auVar14 [16];
  undefined1 in_ZMM6 [64];
  undefined1 auVar15 [64];
  undefined1 auVar16 [64];
  undefined1 auVar17 [16];
  undefined1 local_88 [12];
  undefined4 uStack_7c;
  undefined1 local_78 [2] [16];
  undefined1 local_58 [16];
  
  local_58 = in_ZMM6._0_16_;
  auVar16 = ZEXT1664(_DAT_18085c4d0);
  do {
    uVar3 = *(uint *)(*(longlong *)(param_1 + 0xe8) + 0x10);
    lVar12 = (longlong)(int)param_2 * 0x20 + (ulonglong)uVar3;
    lVar4 = (&DAT_182c2ccc0)[uVar3 >> 0x1c];
    lVar1 = lVar4 + lVar12 * 4;
    for (; param_4 < 4; param_4 = param_4 + 1) {
      uVar3 = param_3 * 2;
      uVar11 = (ulonglong)(*(uint *)(lVar1 + 0x7c) >> (uVar3 & 0x1f) & 3);
      uVar2 = *(undefined4 *)(lVar1 + (longlong)param_3 * 4);
      auVar13._4_4_ = uVar2;
      auVar13._0_4_ = uVar2;
      auVar13._8_4_ = uVar2;
      auVar13._12_4_ = uVar2;
      auVar5 = vsubps_avx(*(undefined1 (*) [16])(param_1 + 0x10 + uVar11 * 0x10),auVar13);
      auVar13 = *(undefined1 (*) [16])(param_1 + 0x50 + uVar11 * 0x10);
      auVar14 = vfmadd231ps_fma(auVar5,auVar13,*param_6);
      auVar14 = vcmpps_avx(*(undefined1 (*) [16])(param_1 + 0xc0),auVar14,2);
      iVar8 = vmovmskps_avx(auVar14);
      if (iVar8 == 0xf) {
        param_3 = 2;
      }
      else if (iVar8 == 0) {
        param_3 = 1;
      }
      else {
        auVar13 = vcmpps_avx(*(undefined1 (*) [16])(param_1 + 0xc0),auVar13,1);
        iVar8 = vmovmskps_avx(auVar13);
        auVar17._0_12_ = ZEXT812(4) << 0x20;
        auVar17._12_4_ = 4;
        auVar13 = vandps_avx(auVar17,auVar16._0_16_);
        auVar14._0_12_ = ZEXT812(0);
        auVar14._12_4_ = 0;
        auVar6 = vfnmadd231ps_fma(auVar14,auVar5,
                                  *(undefined1 (*) [16])(param_1 + 0x80 + uVar11 * 0x10));
        auVar15 = ZEXT1664(auVar6);
        auVar14 = vpcmpgtd_avx(auVar17,auVar16._0_16_);
        auVar5 = vpermilps_avx(*param_6,auVar13);
        auVar5 = vandnps_avx(auVar14,auVar5);
        auVar6 = vpermilps_avx(auVar6,auVar13);
        auVar14 = vandps_avx(auVar6,auVar14);
        local_78[0] = vorps_avx(auVar5,auVar14);
        cVar7 = FUN_1802eb130(param_1,param_2,(2 - (uint)(iVar8 == 0xf)) + uVar3,param_4 + 1,
                              0xffffffff,local_78,auVar13);
        if (cVar7 != '\0') {
          return 1;
        }
        auVar13 = vcmpps_avx(auVar15._0_16_,*(undefined1 (*) [16])(param_1 + 0xb0),1);
        iVar10 = vmovmskps_avx(auVar13);
        if (iVar10 == 0) {
          return 0;
        }
        local_88 = ZEXT812(5) << 0x20;
        local_88 = stack0xffffffffffffff7c << 0x20;
        uStack_7c = 5;
        auVar13 = vandps_avx(_local_88,auVar16._0_16_);
        auVar14 = vpcmpgtd_avx(_local_88,auVar16._0_16_);
        auVar5 = vpermilps_avx(auVar15._0_16_,auVar13);
        auVar5 = vandnps_avx(auVar14,auVar5);
        auVar6 = vpermilps_avx(*param_6,auVar13);
        auVar14 = vandps_avx(auVar6,auVar14);
        auVar14 = vorps_avx(auVar5,auVar14);
        *param_6 = auVar14;
        param_3 = (iVar8 == 0xf) + 1;
        _local_88 = auVar13;
      }
      param_3 = param_3 + uVar3;
    }
    param_4 = 0;
    param_2 = *(uint *)(lVar4 + (param_3 + lVar12) * 4);
    if ((param_2 & 0xc0000000) != 0) {
      if ((int)param_2 < 0) {
        return 0;
      }
      local_78[0] = *param_6;
      uVar9 = FUN_1802eb3d0(param_1,param_2 & 0xbfffffff,local_78);
      return uVar9;
    }
    param_3 = param_4;
  } while (param_2 != 0);
                    /* WARNING: Read-only address (ram,0x00018085c4d0) is written */
  return 0;
}


