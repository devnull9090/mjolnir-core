// FUN_180441f00 at 180441f00 (rva 0x441f00)

undefined8 * FUN_180441f00(undefined8 *param_1)

{
  longlong lVar1;
  longlong *plVar2;
  undefined1 uVar3;
  undefined8 *puVar4;
  
  lVar1 = param_1[1];
  plVar2 = (longlong *)*param_1;
  puVar4 = (undefined8 *)((longlong)param_1 + 0x1fU & 0xfffffffffffffff8);
  *puVar4 = &PTR_FUN_180896eb8;
  *(undefined1 *)(puVar4 + 1) = 0;
  puVar4[2] = plVar2;
  puVar4[3] = lVar1 + 0xc;
  puVar4[4] = 0;
  uVar3 = (**(code **)(*plVar2 + 0x50))();
  *(undefined1 *)(puVar4 + 1) = uVar3;
  *puVar4 = &PTR_FUN_180896e28;
  puVar4[5] = 0;
  param_1[9] = puVar4;
  *(undefined1 *)(param_1 + 2) = 0;
  return puVar4;
}


