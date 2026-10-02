// FUN_1802eb3d0 at 1802eb3d0 (rva 0x2eb3d0)

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

undefined8 FUN_1802eb3d0(undefined1 (*param_1) [16],uint param_2,undefined1 (*param_3) [16])

{
  ushort *puVar1;
  undefined1 auVar2 [16];
  longlong lVar3;
  uint *puVar4;
  uint *puVar5;
  undefined1 auVar6 [16];
  bool bVar7;
  bool bVar8;
  bool bVar9;
  char cVar10;
  ushort uVar11;
  int iVar12;
  int iVar13;
  uint uVar14;
  longlong lVar15;
  longlong lVar16;
  float *pfVar17;
  uint uVar18;
  longlong lVar19;
  uint uVar20;
  longlong lVar21;
  uint uVar22;
  uint *puVar23;
  undefined2 uVar24;
  ushort uVar25;
  uint uVar26;
  char cVar27;
  float fVar28;
  undefined1 auVar29 [16];
  undefined1 in_ZMM6 [64];
  undefined1 auVar30 [64];
  undefined1 auVar31 [64];
  undefined1 auVar32 [64];
  undefined8 unaff_XMM9_Qa;
  undefined8 unaff_XMM9_Qb;
  undefined8 unaff_XMM10_Qa;
  undefined8 unaff_XMM10_Qb;
  undefined8 unaff_XMM11_Qa;
  undefined8 unaff_XMM11_Qb;
  undefined1 auVar33 [16];
  undefined8 unaff_XMM12_Qa;
  undefined8 unaff_XMM12_Qb;
  undefined1 auVar34 [16];
  undefined1 local_d8 [16];
  undefined1 local_c8 [16];
  undefined1 local_b8 [16];
  undefined8 local_a8;
  undefined8 uStack_a0;
  undefined8 local_98;
  undefined8 uStack_90;
  undefined8 local_88;
  undefined8 uStack_80;
  undefined8 local_78;
  undefined8 uStack_70;
  undefined1 local_48 [16];
  
  local_48 = in_ZMM6._0_16_;
  if ((param_2 >> 0x17 & 1) == 0) {
    auVar32 = ZEXT1664(_DAT_1807b0400);
    auVar31 = ZEXT1664(_DAT_18085c4d0);
    do {
      uVar14 = *(uint *)(*(longlong *)(param_1[0xe] + 8) + 4);
      lVar19 = (ulonglong)uVar14 + (ulonglong)(param_2 & 0x7fffff) * 2;
      uVar20 = *(uint *)(*(longlong *)(param_1[0xe] + 8) + 0x1c);
      puVar1 = (ushort *)((&DAT_182c2ccc0)[uVar14 >> 0x1c] + lVar19 * 4);
      auVar2 = *(undefined1 (*) [16])
                ((&DAT_182c2ccc0)[uVar20 >> 0x1c] +
                ((ulonglong)uVar20 +
                (ulonglong)*(ushort *)((&DAT_182c2ccc0)[uVar14 >> 0x1c] + lVar19 * 4) * 4) * 4);
      auVar34 = vdpps_avx(auVar2,*param_1,0x7f);
      auVar6 = vpermilps_avx(auVar2,0xff);
      auVar6 = vsubps_avx(auVar34,auVar6);
      auVar34 = vdpps_avx(param_1[4],auVar2,0x7f);
      auVar2 = vfmadd231ps_fma(auVar6,auVar34,*param_3);
      auVar2 = vcmpps_avx(param_1[0xc],auVar2,2);
      iVar12 = vmovmskps_avx(auVar2);
      if (iVar12 == 0xf) {
        iVar12 = *(int *)(puVar1 + 2);
      }
      else if (iVar12 == 0) {
        iVar12 = *(int *)((longlong)puVar1 + 1);
      }
      else {
        auVar2 = vdivps_avx(auVar32._0_16_,auVar34);
        auVar29._0_12_ = ZEXT812(0);
        auVar29._12_4_ = 0;
        auVar29 = vfnmadd231ps_fma(auVar29,auVar2,auVar6);
        auVar30 = ZEXT1664(auVar29);
        auVar2 = vcmpps_avx(param_1[0xc],auVar34,2);
        iVar12 = vmovmskps_avx(auVar2);
        local_b8._0_12_ = ZEXT812(4) << 0x20;
        local_b8._12_4_ = 4;
        auVar2 = vandps_avx(local_b8,auVar31._0_16_);
        auVar34 = vpcmpgtd_avx(local_b8,auVar31._0_16_);
        auVar6 = vpermilps_avx(*param_3,auVar2);
        auVar6 = vandnps_avx(auVar34,auVar6);
        auVar29 = vpermilps_avx(auVar29,auVar2);
        auVar34 = vandps_avx(auVar29,auVar34);
        local_d8 = vorps_avx(auVar6,auVar34);
        lVar19 = 1;
        if (iVar12 != 0xf) {
          lVar19 = 4;
        }
        local_b8 = auVar2;
        cVar27 = FUN_1802eb3d0(param_1,*(int *)((longlong)puVar1 + lVar19) >> 8,local_d8);
        if (cVar27 != '\0') {
          return 1;
        }
        auVar2 = vcmpps_avx(auVar30._0_16_,param_1[0xb],2);
        iVar13 = vmovmskps_avx(auVar2);
        if (iVar13 != 0xf) {
          return 0;
        }
        auVar2 = *param_3;
        *(uint *)(param_1[0x11] + 8) = (uint)*puVar1;
        lVar19 = 1;
        local_c8._0_12_ = ZEXT812(5) << 0x20;
        if (iVar12 == 0xf) {
          lVar19 = 4;
        }
        local_c8._12_4_ = 5;
        auVar34 = vandps_avx(local_c8,auVar31._0_16_);
        iVar12 = *(int *)((longlong)puVar1 + lVar19);
        auVar29 = vpcmpgtd_avx(local_c8,auVar31._0_16_);
        auVar6 = vpermilps_avx(auVar30._0_16_,auVar34);
        auVar6 = vandnps_avx(auVar29,auVar6);
        auVar2 = vpermilps_avx(auVar2,auVar34);
        auVar2 = vandps_avx(auVar2,auVar29);
        auVar2 = vorps_avx(auVar6,auVar2);
        *param_3 = auVar2;
        local_c8 = auVar34;
      }
      param_2 = iVar12 >> 8;
    } while ((param_2 >> 0x17 & 1) == 0);
  }
  uVar14 = 0xffffffff;
  local_c8._0_8_ = 0xffffffff;
  cVar27 = '\x03';
  bVar7 = false;
  if (param_2 != 0xffffffff) {
    uVar14 = param_2 & 0x7fffff;
    local_c8._0_8_ = CONCAT44(0,uVar14);
    uVar20 = *(uint *)(*(longlong *)(param_1[0xe] + 8) + 0x28);
    cVar27 = (*(byte *)((&DAT_182c2ccc0)[uVar20 >> 0x1c] +
                       ((ulonglong)uVar20 + CONCAT44(0,uVar14) * 2) * 4) & 1) + 1;
  }
  uVar20 = *(uint *)param_1[0xe];
  local_78 = unaff_XMM9_Qa;
  uStack_70 = unaff_XMM9_Qb;
  local_88 = unaff_XMM10_Qa;
  uStack_80 = unaff_XMM10_Qb;
  local_98 = unaff_XMM11_Qa;
  uStack_90 = unaff_XMM11_Qb;
  local_a8 = unaff_XMM12_Qa;
  uStack_a0 = unaff_XMM12_Qb;
  if ((((uVar20 & 1) == 0) || (1 < (byte)(param_1[0x11][4] - 1))) || (cVar27 != '\x03')) {
    if ((((uVar20 & 2) == 0) || (param_1[0x11][4] != '\x03')) || (1 < (byte)(cVar27 - 1U))) {
      if ((((uVar20 & 4) != 0) || (param_1[0x11][4] != '\x02')) || (cVar27 != '\x02'))
      goto LAB_1802eba0d;
      if ((uVar20 & 1) != 0) {
        uVar14 = *(uint *)param_1[0x11];
      }
      bVar7 = true;
    }
  }
  else {
    uVar14 = *(uint *)param_1[0x11];
  }
  if (uVar14 != 0xffffffff) {
    lVar3 = *(longlong *)(param_1[0xe] + 8);
    auVar31 = ZEXT1664(*param_3);
    lVar19 = (&DAT_182c2ccc0)[*(uint *)(lVar3 + 0x28) >> 0x1c] +
             ((ulonglong)*(uint *)(lVar3 + 0x28) + (longlong)(int)uVar14 * 2) * 4;
    if (((lVar19 != 0) && (uVar20 = *(uint *)(lVar19 + 4), uVar20 != 0xffffffff)) &&
       (uVar26 = *(ushort *)(lVar19 + 2) + uVar20, uVar20 < uVar26)) {
      uVar18 = *(uint *)(param_1[0x11] + 8);
      lVar21 = *(longlong *)param_1[0x10];
      auVar32 = ZEXT1664(_DAT_1808f38d0);
      fVar28 = 0.0;
      lVar19 = (&DAT_182c2ccc0)[*(uint *)(lVar3 + 0x34) >> 0x1c] +
               (ulonglong)*(uint *)(lVar3 + 0x34) * 4;
      do {
        auVar2 = local_b8;
        lVar15 = 0;
        auVar34 = auVar31._0_16_;
        uVar25 = *(ushort *)(lVar19 + (longlong)(int)uVar20 * 4);
        if ((uVar25 & 0x7fff) == uVar18) {
          puVar23 = (uint *)((&DAT_182c2ccc0)[*(uint *)(lVar3 + 0x1c) >> 0x1c] +
                            (longlong)(int)uVar18 * 0x10 + (ulonglong)*(uint *)(lVar3 + 0x1c) * 4);
          auVar33 = auVar32._0_16_;
          auVar6 = vandps_avx(ZEXT416(puVar23[1]),auVar33);
          auVar29 = vandps_avx(ZEXT416(puVar23[2]),auVar33);
          auVar33 = vandps_avx(ZEXT416(*puVar23),auVar33);
          if ((auVar29._0_4_ < auVar6._0_4_) || (auVar29._0_4_ < auVar33._0_4_)) {
            if (auVar6._0_4_ < auVar33._0_4_) {
              uVar24 = 0;
              lVar16 = lVar15;
            }
            else {
              lVar15 = 4;
              uVar24 = 1;
              lVar16 = 2;
            }
          }
          else {
            lVar15 = 8;
            uVar24 = 2;
            lVar16 = 4;
          }
          uVar25 = uVar25 >> 0xf;
          puVar4 = *(uint **)(param_1[0xd] + 8);
          puVar5 = *(uint **)param_1[0xd];
          uVar11 = (ushort)(fVar28 < *(float *)(lVar15 + (longlong)puVar23));
          lVar16 = (ulonglong)(uVar11 ^ uVar25) + lVar16;
          auVar6 = vfmadd213ss_fma(ZEXT416(*puVar4),auVar34,ZEXT416(*puVar5));
          auVar29 = vfmadd213ss_fma(ZEXT416(puVar4[1]),auVar34,ZEXT416(puVar5[1]));
          local_b8._4_4_ = auVar29._0_4_;
          local_b8._0_4_ = auVar6._0_4_;
          auVar6 = vfmadd213ss_fma(auVar34,ZEXT416(puVar4[2]),ZEXT416(puVar5[2]));
          local_b8._12_4_ = auVar2._12_4_;
          local_b8._8_4_ = auVar6._0_4_;
          uVar18 = (uint)*(short *)(lVar19 + 2 + (longlong)(int)uVar20 * 4);
          local_d8._4_4_ =
               *(uint *)(local_b8 + (longlong)*(short *)(&DAT_1807e2662 + lVar16 * 6) * 4);
          local_d8._0_4_ =
               *(float *)(local_b8 + (longlong)*(short *)(&DAT_1807e2660 + lVar16 * 6) * 4);
          if ((uVar18 >> 0xf & 1) == 0) {
            do {
              pfVar17 = (float *)((ulonglong)(uVar18 & 0x7fff) * 0x10 +
                                 (&DAT_182c2ccc0)[*(uint *)(lVar3 + 0x40) >> 0x1c] +
                                 (ulonglong)*(uint *)(lVar3 + 0x40) * 4);
              auVar2 = vfmadd231ss_fma(ZEXT416((uint)(*(float *)(local_b8 +
                                                                (longlong)
                                                                *(short *)(&DAT_1807e2660 +
                                                                          lVar16 * 6) * 4) *
                                                     *pfVar17)),
                                       ZEXT416(*(uint *)(local_b8 +
                                                        (longlong)
                                                        *(short *)(&DAT_1807e2662 + lVar16 * 6) * 4)
                                              ),ZEXT416((uint)pfVar17[1]));
              uVar18 = (uint)*(short *)((longlong)pfVar17 +
                                       (ulonglong)(fVar28 <= auVar2._0_4_ - pfVar17[2]) * 2 + 0xc);
            } while ((uVar18 >> 0xf & 1) == 0);
          }
          uVar22 = 0xffffffff;
          if (uVar18 != 0xffffffff) {
            uVar22 = uVar18 & 0x7fff;
          }
          if (((lVar21 == 0) ||
              (uVar18 = (uint)*(short *)((longlong)(int)uVar22 * 0xe + 4 +
                                        (&DAT_182c2ccc0)[*(uint *)(lVar3 + 0x4c) >> 0x1c] +
                                        (ulonglong)*(uint *)(lVar3 + 0x4c) * 4),
              uVar18 == 0xffffffff)) ||
             ((*(uint *)(lVar21 + (ulonglong)(uVar18 >> 5) * 4) >> (uVar18 & 0x1f) & 1) != 0)) {
            lVar21 = (longlong)(int)uVar22 * 0xe;
            if (!bVar7) {
LAB_1802eba7b:
              if (uVar22 != 0xffffffff) {
                uVar20 = *(uint *)param_1[0xe];
                lVar19 = (&DAT_182c2ccc0)[*(uint *)(lVar3 + 0x4c) >> 0x1c] +
                         (ulonglong)*(uint *)(lVar3 + 0x4c) * 4;
                uVar25 = *(ushort *)(lVar19 + 10 + lVar21);
                if (((uVar25 & 2) == 0) || ((uVar20 & 8) == 0)) {
                  bVar7 = false;
                }
                else {
                  bVar7 = true;
                }
                if (((uVar25 & 8) == 0) || ((uVar20 & 0x10) == 0)) {
                  bVar8 = false;
                }
                else {
                  bVar8 = true;
                }
                if (((uVar25 >> 8 & 1) == 0) || ((uVar20 & 0x40) != 0)) {
                  bVar9 = false;
                }
                else {
                  bVar9 = true;
                }
                if ((!bVar7) && (!bVar8 && !bVar9)) {
                  **(undefined4 **)(param_1[0x10] + 8) = auVar34._0_4_;
                  local_b8 = ZEXT816(0);
                  lVar3 = *(longlong *)(param_1[0xe] + 8);
                  auVar2 = vpermilps_avx(auVar34,local_b8);
                  param_1[0xb] = auVar2;
                  uVar20 = *(uint *)(lVar3 + 0x1c);
                  *(ulonglong *)(*(longlong *)(param_1[0x10] + 8) + 8) =
                       (&DAT_182c2ccc0)[uVar20 >> 0x1c] +
                       ((ulonglong)uVar20 + (longlong)*(int *)(param_1[0x11] + 8) * 4) * 4;
                  *(uint *)(*(longlong *)(param_1[0x10] + 8) + 0x10) = uVar14;
                  *(uint *)(*(longlong *)(param_1[0x10] + 8) + 0x14) = uVar22;
                  *(uint *)(*(longlong *)(param_1[0x10] + 8) + 0x18) =
                       (uint)*(ushort *)(lVar19 + lVar21);
                  *(byte *)(*(longlong *)(param_1[0x10] + 8) + 0x1c) =
                       *(byte *)(lVar19 + 10 + lVar21) >> 7;
                  *(undefined2 *)(*(longlong *)(param_1[0x10] + 8) + 0x1e) =
                       *(undefined2 *)(lVar19 + 10 + lVar21);
                  *(undefined1 *)(*(longlong *)(param_1[0x10] + 8) + 0x20) =
                       *(undefined1 *)(lVar19 + 6 + lVar21);
                  *(undefined1 *)(*(longlong *)(param_1[0x10] + 8) + 0x21) =
                       *(undefined1 *)(lVar19 + 8 + lVar21);
                  *(undefined2 *)(*(longlong *)(param_1[0x10] + 8) + 0x22) =
                       *(undefined2 *)(lVar19 + 4 + lVar21);
                  return 1;
                }
              }
              break;
            }
            auVar2 = vfmadd231ss_fma(ZEXT416((uint)((float)puVar23[1] * (float)puVar4[1])),
                                     ZEXT416(*puVar4),ZEXT416(*puVar23));
            auVar2 = vfmadd231ss_fma(auVar2,ZEXT416(puVar23[2]),ZEXT416(puVar4[2]));
            if (fVar28 < auVar2._0_4_ == uVar25) {
              cVar10 = FUN_1802f0170(lVar3,*(undefined2 *)param_1[0xf],
                                     *(undefined8 *)(param_1[0xf] + 8),uVar22,uVar24,
                                     uVar11 != uVar25,local_d8);
              auVar34 = auVar31._0_16_;
              if (cVar10 != '\0') goto LAB_1802eba7b;
            }
            lVar21 = *(longlong *)param_1[0x10];
          }
          uVar18 = *(uint *)(param_1[0x11] + 8);
        }
        uVar20 = uVar20 + 1;
      } while (uVar20 < uVar26);
    }
  }
LAB_1802eba0d:
  *(undefined4 *)param_1[0x11] = local_c8._0_4_;
  param_1[0x11][4] = cVar27;
                    /* WARNING: Read-only address (ram,0x0001807b0400) is written */
                    /* WARNING: Read-only address (ram,0x00018085c4d0) is written */
                    /* WARNING: Read-only address (ram,0x0001808f38d0) is written */
  return 0;
}


