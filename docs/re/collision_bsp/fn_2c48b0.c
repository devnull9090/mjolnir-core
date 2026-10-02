// FUN_1802c48b0 at 1802c48b0 (rva 0x2c48b0)

undefined8
FUN_1802c48b0(undefined4 *param_1,int param_2,uint param_3,undefined4 param_4,float *param_5,
             float *param_6,undefined4 *param_7)

{
  short sVar1;
  uint uVar2;
  longlong lVar3;
  undefined1 auVar4 [16];
  float fVar5;
  char cVar6;
  undefined4 uVar7;
  undefined8 *puVar8;
  undefined8 uVar9;
  undefined2 *puVar10;
  undefined8 uVar11;
  float *pfVar12;
  float extraout_XMM0_Da;
  float fVar13;
  float fVar14;
  undefined1 auVar15 [16];
  undefined1 auVar16 [16];
  float fVar17;
  float fVar18;
  undefined1 auVar19 [16];
  undefined1 auVar20 [16];
  undefined1 auVar21 [16];
  undefined1 auVar22 [16];
  undefined1 auVar23 [16];
  undefined8 uVar24;
  undefined4 local_f0;
  undefined4 local_ec;
  undefined4 local_e8;
  undefined4 local_e0;
  undefined4 local_dc;
  undefined4 local_d8;
  undefined8 local_c8;
  undefined8 uStack_c0;
  undefined1 local_b8 [34];
  short local_96;
  
  pfVar12 = (float *)((longlong)param_2 * 0x94 + *(longlong *)(param_1 + 4));
  cVar6 = FUN_1801a27f0(param_5,param_6,pfVar12 + 0x19,pfVar12[0x1c]);
  if (cVar6 == '\0') {
    return 0;
  }
  FUN_1801a3290();
  if ((float)param_7[1] <= extraout_XMM0_Da) {
    uVar11 = 0;
  }
  else {
    sVar1 = *(short *)(pfVar12 + 0xd);
    uVar2 = *(uint *)(*(longlong *)(param_1 + 0x18) + 0x1c);
    lVar3 = (&DAT_182c2ccc0)[uVar2 >> 0x1c];
    FUN_1802c2200(&local_c8,*(undefined8 *)(param_1 + 2),(longlong)sVar1 & 0xffffffff,0);
    fVar18 = param_5[1] - pfVar12[0xb];
    auVar19 = ZEXT416((uint)fVar18);
    fVar14 = *pfVar12;
    fVar17 = *param_5 - pfVar12[10];
    fVar5 = param_5[2] - pfVar12[0xc];
    auVar21 = ZEXT416((uint)fVar5);
    auVar15 = ZEXT416((uint)fVar14);
    auVar4 = vmaxss_avx(auVar15,ZEXT416(0x38d1b717));
    auVar23._0_12_ = ZEXT812(0);
    auVar23._12_4_ = 0;
    if (fVar14 == 1.0) {
      auVar16 = vminss_avx(auVar15,ZEXT416(0xb8d1b717));
    }
    else {
      auVar19._4_12_ = SUB6012((undefined1  [60])0x0,0);
      auVar21._4_12_ = SUB6012((undefined1  [60])0x0,0);
      if (fVar14 < 0.0) {
        auVar16 = vminss_avx(ZEXT416((uint)fVar14),ZEXT416(0xb8d1b717));
        fVar13 = auVar16._0_4_;
        fVar17 = fVar17 / fVar13;
        auVar19._0_4_ = fVar18 / fVar13;
        auVar21._0_4_ = fVar5 / fVar13;
      }
      else {
        auVar16 = vminss_avx(ZEXT416((uint)fVar14),ZEXT416(0xb8d1b717));
        fVar13 = auVar4._0_4_;
        fVar17 = fVar17 / fVar13;
        auVar19._0_4_ = fVar18 / fVar13;
        auVar21._0_4_ = fVar5 / fVar13;
      }
    }
    auVar20 = vfmadd231ss_fma(ZEXT416((uint)(pfVar12[1] * fVar17)),auVar19,ZEXT416((uint)pfVar12[2])
                             );
    auVar20 = vfmadd231ss_fma(auVar20,auVar21,ZEXT416((uint)pfVar12[3]));
    local_e0 = auVar20._0_4_;
    auVar20 = vfmadd231ss_fma(ZEXT416((uint)(pfVar12[4] * fVar17)),auVar19,ZEXT416((uint)pfVar12[5])
                             );
    auVar20 = vfmadd231ss_fma(auVar20,auVar21,ZEXT416((uint)pfVar12[6]));
    local_dc = auVar20._0_4_;
    auVar19 = vfmadd231ss_fma(ZEXT416((uint)(pfVar12[7] * fVar17)),auVar19,ZEXT416((uint)pfVar12[8])
                             );
    auVar19 = vfmadd231ss_fma(auVar19,auVar21,ZEXT416((uint)pfVar12[9]));
    fVar18 = *param_6;
    auVar20 = ZEXT416((uint)param_6[1]);
    auVar22 = ZEXT416((uint)param_6[2]);
    local_d8 = auVar19._0_4_;
    if (fVar14 != 1.0) {
      auVar15 = vcmpss_avx(auVar23,auVar15,2);
      auVar4 = vblendvps_avx(auVar16,auVar4,auVar15);
      fVar14 = auVar4._0_4_;
      fVar18 = fVar18 / fVar14;
      auVar20._0_4_ = param_6[1] / fVar14;
      auVar20._4_12_ = SUB6012((undefined1  [60])0x0,0);
      auVar22._0_4_ = param_6[2] / fVar14;
      auVar22._4_12_ = SUB6012((undefined1  [60])0x0,0);
    }
    auVar4 = vfmadd231ss_fma(ZEXT416((uint)(pfVar12[1] * fVar18)),auVar20,ZEXT416((uint)pfVar12[2]))
    ;
    auVar4 = vfmadd231ss_fma(auVar4,auVar22,ZEXT416((uint)pfVar12[3]));
    local_f0 = auVar4._0_4_;
    auVar4 = vfmadd231ss_fma(ZEXT416((uint)(pfVar12[7] * fVar18)),auVar20,ZEXT416((uint)pfVar12[8]))
    ;
    auVar4 = vfmadd231ss_fma(auVar4,auVar22,ZEXT416((uint)pfVar12[9]));
    auVar15 = vfmadd231ss_fma(ZEXT416((uint)(pfVar12[4] * fVar18)),auVar20,ZEXT416((uint)pfVar12[5])
                             );
    auVar15 = vfmadd231ss_fma(auVar15,auVar22,ZEXT416((uint)pfVar12[6]));
    local_e8 = auVar4._0_4_;
    local_ec = auVar15._0_4_;
    uVar11 = local_c8;
    uVar24 = uStack_c0;
    if (((param_3 & 0x10) != 0) &&
       (*(int *)(lVar3 + 0xe0 + ((longlong)sVar1 * 0x51 + (ulonglong)uVar2) * 4) != 0)) {
      puVar8 = (undefined8 *)
               FUN_1802c2200(&local_c8,*(undefined8 *)(param_1 + 2),(int)*(short *)(pfVar12 + 0xd),1
                            );
      uVar11 = *puVar8;
      uVar24 = puVar8[1];
    }
    uVar7 = *param_1;
    local_c8 = uVar11;
    uStack_c0 = uVar24;
    uVar9 = FUN_180267830(uVar7,param_2);
    uVar7 = FUN_180267950(uVar7,param_2);
    cVar6 = FUN_1802e9d20(param_4,&local_c8,0,uVar7,uVar9,&local_e0,&local_f0,param_7[1],local_b8);
    if (cVar6 == '\0') {
      uVar11 = 0;
    }
    else {
      *param_7 = 3;
      *(undefined8 *)(param_7 + 6) = uVar11;
      *(undefined8 *)(param_7 + 8) = uVar24;
      if (local_96 == -1) {
        puVar10 = &DAT_180bcf3c8;
      }
      else {
        puVar10 = (undefined2 *)
                  ((&DAT_182c2ccc0)[*(uint *)(*(longlong *)(param_1 + 2) + 0x5c) >> 0x1c] +
                   ((ulonglong)*(uint *)(*(longlong *)(param_1 + 2) + 0x5c) + (longlong)local_96 * 6
                   ) * 4 + 0x10);
      }
      *(undefined2 *)(param_7 + 10) = *puVar10;
      param_7[0xf] = param_2;
      param_7[0x10] = 0xffffffff;
      param_7[0x13] = *param_1;
      FUN_1802c38b0(param_7,local_b8,pfVar12);
      uVar11 = 1;
    }
  }
  return uVar11;
}


