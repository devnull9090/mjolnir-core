// FUN_180441f70 at 180441f70 (rva 0x441f70)

undefined1
FUN_180441f70(undefined8 *param_1,undefined4 param_2,undefined4 param_3,longlong *param_4)

{
  char cVar1;
  undefined1 uVar2;
  undefined4 local_res20;
  undefined4 uStackX_24;
  undefined4 local_18;
  undefined4 local_14;
  undefined4 local_10;
  
  (**(code **)(*param_4 + 0x48))(param_4,&local_res20);
  uVar2 = 0;
  local_10 = local_res20;
  local_18 = param_2;
  local_14 = param_3;
  cVar1 = (**(code **)(*(longlong *)*param_1 + 0x38))((longlong *)*param_1,param_1[1]);
  if (cVar1 != '\0') {
    cVar1 = (**(code **)(*(longlong *)*param_1 + 0x80))((longlong *)*param_1,&local_18,0xc,1,0);
    if (cVar1 != '\0') {
      param_1[1] = param_1[1] + CONCAT44(uStackX_24,local_res20) + 0xc;
      uVar2 = (**(code **)(*(longlong *)*param_1 + 0x38))((longlong *)*param_1,param_1[1]);
    }
  }
  (*(code *)**(undefined8 **)param_1[9])((undefined8 *)param_1[9],0);
  param_1[9] = 0;
  *(undefined1 *)(param_1 + 2) = 1;
  return uVar2;
}


