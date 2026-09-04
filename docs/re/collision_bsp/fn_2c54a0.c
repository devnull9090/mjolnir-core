// FUN_1802c54a0 at 1802c54a0 (rva 0x2c54a0)

char FUN_1802c54a0(undefined8 *param_1,undefined8 param_2,ulonglong param_3,uint param_4,
                  longlong param_5)

{
  longlong lVar1;
  float *pfVar2;
  short sVar3;
  int iVar4;
  longlong lVar5;
  uint *puVar6;
  uint *puVar7;
  undefined1 auVar8 [16];
  undefined1 auVar9 [16];
  undefined1 auVar10 [16];
  longlong lVar11;
  uint uVar12;
  int iVar13;
  ulonglong uVar14;
  char cVar15;
  uint uVar16;
  ulonglong uVar17;
  uint uVar18;
  longlong lVar19;
  float *pfVar20;
  int iVar21;
  longlong lVar22;
  int iVar23;
  float fVar24;
  undefined1 auVar25 [64];
  undefined1 auVar26 [64];
  undefined1 auVar27 [64];
  undefined1 auVar28 [16];
  undefined1 auVar29 [64];
  undefined1 auVar30 [64];
  
  lVar11 = param_5;
  cVar15 = '\0';
  if ((*(int *)(param_5 + 0x230) != -1) && (((param_3 & 8) != 0 || ((param_3 >> 0x20 & 1) != 0)))) {
    uVar17 = 0;
    uVar16 = 0xffffffff;
    iVar4 = *(int *)(param_5 + 0x228);
    param_5._0_4_ = 0;
    if (0 < iVar4) {
      lVar22 = 0x180000000;
      auVar25 = ZEXT464(0);
      auVar26 = ZEXT464(0);
      auVar27 = ZEXT464(0);
      auVar30 = ZEXT464(0x3f800000);
      auVar29 = ZEXT1264(ZEXT812(0));
      do {
        if (*(char *)(lVar11 + 0xa3e + uVar17 * 0xc) != '\0') {
          uVar12 = *(uint *)(lVar22 + 0x13d45cc + (longlong)(int)param_4 * 0x490);
          lVar1 = (ulonglong)uVar12 + (longlong)*(short *)(lVar11 + 0xa36 + uVar17 * 0xc) * 5;
          lVar5 = *(longlong *)(lVar22 + 0x2c2ccc0 + (ulonglong)(uVar12 >> 0x1c) * 8);
          uVar12 = (int)(1L << ((ulonglong)(uint)(int)*(short *)(lVar11 + 0xa38 + uVar17 * 0xc) &
                               0x3f)) - 1U & *(uint *)(lVar5 + 0xc + lVar1 * 4);
          uVar14 = ((ulonglong)uVar12 & 0x5555555555555555) +
                   ((ulonglong)(uVar12 >> 1) & 0x5555555555555555);
          uVar14 = (uVar14 >> 2 & 0x3333333333333333) + (uVar14 & 0x3333333333333333);
          uVar14 = (uVar14 & 0xf0f0f0f0f0f0f0f) + (uVar14 >> 4 & 0xf0f0f0f0f0f0f0f);
          lVar19 = (uVar14 >> 8 & 0xff00ff00ff00ff) + (uVar14 & 0xff00ff00ff00ff);
          uVar12 = *(uint *)((&DAT_1813d45a8)[(longlong)(int)param_4 * 0x92] + 0x74);
          lVar22 = 0x180000000;
          pfVar2 = (float *)((&DAT_182c2ccc0)[uVar12 >> 0x1c] +
                            ((ulonglong)uVar12 +
                            (longlong)
                            (int)((int)*(short *)(lVar5 + 10 + lVar1 * 4) +
                                  (int)((ulonglong)lVar19 >> 0x10) + ((uint)lVar19 & 0xffff)) * 6) *
                            4);
          pfVar20 = pfVar2;
          fVar24 = (float)FUN_1801a3290(*param_1,param_1[1]);
          if (fVar24 < *(float *)(param_1[4] + 4)) {
            iVar23 = (int)*(short *)(lVar11 + 0xa3a + uVar17 * 0xc);
            iVar21 = *(short *)(lVar11 + 0xa3c + uVar17 * 0xc) + iVar23;
            pfVar20 = pfVar2;
            uVar12 = uVar16;
            uVar18 = 0xffffffff;
            if (iVar23 < iVar21) {
              do {
                iVar13 = *(int *)(lVar11 + 0x234 + (longlong)iVar23 * 4);
                if (iVar13 == -1) {
                  uVar16 = 0xffffffff;
                }
                else {
                  uVar16 = *(uint *)((&DAT_1813d45a8)[(longlong)(int)param_4 * 0x92] + 0x68);
                  uVar16 = (uint)*(byte *)((longlong)iVar13 +
                                          *(longlong *)
                                           (lVar22 + 0x2c2ccc0 + (ulonglong)(uVar16 >> 0x1c) * 8) +
                                          (ulonglong)uVar16 * 4) << 8 | param_4;
                }
                if ((uVar18 != uVar16) && (((param_3 & 0x100000000) != 0 || ((param_3 & 8) != 0))))
                {
                  if (uVar16 != uVar12) {
                    sVar3 = *(short *)(lVar11 + 0xa34 + uVar17 * 0xc);
                    while (iVar13 = (int)sVar3, iVar13 != -1) {
                      *(undefined2 *)(lVar11 + 0x28 + (longlong)iVar13 * 2) = 0xffff;
                      sVar3 = *(short *)(lVar11 + 0xa34 + (longlong)iVar13 * 0xc);
                    }
                  }
                  if (((~((int)uVar16 >> 7) & 1U) - 1 | uVar16 & 0xff) != 0xffffffff) {
                    iVar13 = FUN_1803e21a0(param_1,lVar11,uVar18,(uint)param_5,uVar16,param_3,
                                           param_2);
                    if (iVar13 != -1) {
                      puVar6 = (uint *)*param_1;
                      cVar15 = '\x01';
                      uVar12 = *(uint *)(param_1[4] + 4);
                      puVar7 = (uint *)param_1[1];
                      auVar10 = vfmadd213ss_fma(ZEXT416(*puVar7),ZEXT416(uVar12),ZEXT416(*puVar6));
                      auVar25 = ZEXT1664(auVar10);
                      auVar10 = vfmadd213ss_fma(ZEXT416(puVar7[1]),ZEXT416(uVar12),
                                                ZEXT416(puVar6[1]));
                      auVar26 = ZEXT1664(auVar10);
                      auVar10 = vfmadd213ss_fma(ZEXT416(puVar7[2]),ZEXT416(uVar12),
                                                ZEXT416(puVar6[2]));
                      auVar27 = ZEXT1664(auVar10);
                    }
                    lVar22 = 0x180000000;
                  }
                  *(ushort *)(lVar11 + 0x28 + uVar17 * 2) = (ushort)(uVar16 >> 8) & 0xff;
                }
                iVar23 = iVar23 + 1;
                uVar12 = uVar16;
                uVar18 = uVar16;
              } while (iVar23 < iVar21);
              uVar17 = (ulonglong)(uint)param_5;
            }
          }
          if (cVar15 != '\0') {
            auVar28 = auVar29._0_16_;
            auVar10 = vcmpss_avx(auVar28,ZEXT416((uint)(auVar25._0_4_ - *pfVar20)),2);
            auVar10 = vblendvps_avx(auVar28,auVar30._0_16_,auVar10);
            auVar8 = vcmpss_avx(auVar28,ZEXT416((uint)(pfVar20[1] - auVar25._0_4_)),2);
            auVar9 = vcmpss_avx(auVar28,ZEXT416((uint)(auVar26._0_4_ - pfVar20[2])),2);
            auVar10 = vblendvps_avx(auVar28,auVar10,auVar8);
            auVar10 = vblendvps_avx(auVar28,auVar10,auVar9);
            auVar8 = vcmpss_avx(auVar28,ZEXT416((uint)(pfVar20[3] - auVar26._0_4_)),2);
            auVar10 = vblendvps_avx(auVar28,auVar10,auVar8);
            auVar8 = vcmpss_avx(auVar28,ZEXT416((uint)(auVar27._0_4_ - pfVar20[4])),2);
            auVar10 = vblendvps_avx(auVar28,auVar10,auVar8);
            auVar8 = vcmpss_avx(auVar28,ZEXT416((uint)(pfVar20[5] - auVar27._0_4_)),2);
            auVar10 = vblendvps_avx(auVar28,auVar10,auVar8);
            if (auVar10._0_4_ == auVar30._0_4_) {
              return cVar15;
            }
          }
        }
        param_5._0_4_ = (int)uVar17 + 1;
        uVar17 = (ulonglong)(uint)param_5;
      } while ((int)(uint)param_5 < iVar4);
    }
    return cVar15;
  }
  return '\0';
}


