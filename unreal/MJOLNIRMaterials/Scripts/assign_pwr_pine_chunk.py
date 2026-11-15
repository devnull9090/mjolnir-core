"""Repair pine chunk management without rebuilding or touching its mesh."""
import unreal

folder='/Game/MJOLNIR/Scenery/PWR'
mesh=unreal.load_asset(folder+'/SM_PWR_MaturePine_A')
label=unreal.load_asset(folder+'/PAL_MJOLNIR_PWR_MaturePine959')
if mesh is None or label is None:raise RuntimeError('Audited pine/label missing')
rules=label.get_editor_property('rules')
before={key:rules.get_editor_property(key) for key in ('chunk_id','priority','apply_recursively')}
rules.set_editor_property('chunk_id',959)
rules.set_editor_property('priority',1000)
rules.set_editor_property('apply_recursively',True)
rules.set_editor_property('cook_rule',unreal.PrimaryAssetCookRule.ALWAYS_COOK)
label.set_editor_property('rules',rules)
label.set_editor_property('label_assets_in_my_directory',False)
label.set_editor_property('explicit_assets',[mesh])
if not unreal.EditorAssetLibrary.save_loaded_asset(label):raise RuntimeError('Label save failed')
unreal.log('MJOLNIR pine chunk label: '+str(before)+' -> recursive priority1000 chunk959; mesh unchanged')
