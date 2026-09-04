// FUN_18043f3a0 at 18043f3a0 (rva 0x43f3a0)

void FUN_18043f3a0(undefined8 param_1,int *param_2,undefined8 param_3,longlong *param_4)

{
  longlong *plVar1;
  longlong lVar2;
  int iVar3;
  
  plVar1 = (longlong *)(**(code **)(*param_4 + 0x10))(param_4);
  lVar2 = (**(code **)(*plVar1 + 0x18))
                    (plVar1,(&DAT_182c2ccc0)[(uint)param_2[2] >> 0x1c] +
                            (ulonglong)(uint)param_2[2] * 4);
  plVar1 = (longlong *)(**(code **)(*plVar1 + 8))(plVar1,lVar2);
  iVar3 = 0;
  if (0 < *param_2) {
    do {
      (**(code **)(*plVar1 + 0x10))
                (plVar1,(longlong)
                        *(int *)(*(longlong *)
                                  ((&DAT_182c2ccc0)[(uint)param_2[2] >> 0x1c] + 0x20 +
                                  (ulonglong)(uint)param_2[2] * 4) + 0x28) * (longlong)iVar3 +
                        (&DAT_182c2ccc0)[(uint)param_2[1] >> 0x1c] + (ulonglong)(uint)param_2[1] * 4
                 ,lVar2,param_4);
      iVar3 = iVar3 + 1;
    } while (iVar3 < *param_2);
  }
  plVar1 = (longlong *)(**(code **)(*param_4 + 0x18))(param_4);
  (**(code **)(*plVar1 + 0x30))
            (plVar1,(&DAT_182c2ccc0)[(uint)param_2[1] >> 0x1c] + (ulonglong)(uint)param_2[1] * 4,
             *(undefined4 *)(lVar2 + 0x38),0);
  param_2[0] = 0;
  param_2[1] = 0;
  return;
}


