"""Build the distributable FT reference from the frozen, private audit inventory.

The input is read-only. The output contains curated explanations and source
references, never the inventory's decompiled bodies or native snapshots.
Changed input requires an explicit review of this generator's frozen digest.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

INVENTORY_SHA256 = "2427487280259db5ae4500c6c06d2cac9b697e9f12cd09a06c959159c33e91fa"
GAME_SHA256 = "e2ae689c7074246ec15858556070bfaa912b1dec51c2c0580b511cc61964bfff"
SHARED_INVENTORY_SHA256 = "4a43b5484b8462045924303a63d045a6e46c63a879cee3e7a919d76301c0a62e"
SOURCE_AST_SHA256 = "86aade36784dadca7bf72a927f934be442c36a7bfa202bc6023651fcef940e76"
EXPECTED_COUNTS = {"functions": 35, "constants": 4, "variables": 55,
                   "rules": 21, "inputs": 88, "outputs": 60,
                   "examples": 16, "mfd": 75, "unknowns": 8}
FUNCTION_EXAMPLES = {
    "abs": "abs(-2)", "ceil": "ceil(1.2)", "clamp": "clamp(2,0,1)",
    "clamp01": "clamp01(2)", "deltaangle": "deltaangle(350,10)",
    "exp": "exp(1)", "floor": "floor(1.8)", "inverselerp": "inverselerp(0,10,5)",
    "lerp": "lerp(0,10,0.5)", "lerpangle": "lerpangle(350,10,0.5)",
    "lerpunclamped": "lerpunclamped(0,10,2)", "log10": "log10(100)",
    "log": "log(8,2)", "max": "max(1,2)", "min": "min(1,2)",
    "pingpong": "pingpong(3,2)", "pow": "pow(2,3)", "repeat": "repeat(3,2)",
    "round": "round(1.2)", "sign": "sign(-2)", "smoothstep": "smoothstep(0,1,0.5)",
    "sqrt": "sqrt(4)", "sin": "sin(90)", "cos": "cos(0)", "tan": "tan(45)",
    "asin": "asin(1)", "acos": "acos(0)", "atan": "atan(1)", "atan2": "atan2(1,0)",
    "format": 'format(12.34,"F1")', "sum": "sum(1)", "rate": "rate(Throttle)",
    "PID": "PID(1,Throttle,1,0,0)", "smooth": "smooth(Throttle,0.5)",
    "ammo": "ammo(SelectedWeapon)",
}

# Script -> Data relations were checked against the frozen Game source hashes.
# The line is a typed property/field, generic base argument, or type constraint;
# this is not a suffix-based guess. Qualified AST inheritance closes the
# Data-class -> partType side without treating native defaults as live values.
SCRIPT_DATA = {
    "ArrestingHookScript": ("ArrestingHookData", 32), "BaseWheelScript": ("BaseWheelData", 124),
    "BeaconLightScript": ("BeaconLightData", 54), "BladedEngineScript": ("BladedEngineData", 263),
    "BombScript": ("BombData", 13), "CameraVantageScript": ("CameraVantageData", 19),
    "CannonScript": ("CannonData", 46), "CarEngineScript": ("CarEngineData", 32),
    "CockpitButtonScript": ("CockpitButtonData", 92), "CockpitScript": ("CockpitData", 17),
    "CockpitSoundScript": ("CockpitSoundData", 13), "CockpitSwitchScript": ("CockpitSwitchData", 79),
    "ControlBaseScript": ("ControlBaseData", 277), "ControlSurfaceScript": ("ControlSurfaceData", 45),
    "CounterMeasureDispenserScript": ("CounterMeasureDispenserData", 18), "DetacherScript": ("DetacherData", 41),
    "EngineScript": ("EngineData", 33), "ExplosiveWeaponScriptBase": ("ExplosiveWeaponBaseData", 10),
    "GaugeScript": ("GaugeData", 53), "GearLegScript": ("GearLegData", 136),
    "GunScript": ("GunData", 70), "GyroscopeScript": ("GyroscopeData", 11),
    "HeliMainRotorScript": ("HeliMainRotorData", 109), "InputControllerScript": ("InputControllerData", 16),
    "JDifferentialScript": ("JDifferentialData", 21), "JEngineScript": ("JEngineData", 77),
    "JTransmissionScript": ("JTransmissionData", 46), "JWheelAssemblyScript": ("JWheelAssemblyData", 85),
    "JWheelScript": ("JWheelData", 55), "JetEngineScript": ("JetEngineData", 53),
    "JointRotatorScript": ("JointRotatorData", 46), "LabelScript": ("LabelData", 54),
    "LightScript": ("BeaconLightData", 57), "MagnetScript": ("MagnetData", 111),
    "MissileScript": ("MissileData", 19), "ParachuteScript": ("ParachuteData", 56),
    "PartModifierScript": ("PartModifierData", 66), "PedalScript": ("PedalData", 34),
    "PropellerAssemblyScript": ("PropellerAssemblyData", 292),
    "ReactionControlNozzleScript": ("ReactionControlNozzleData", 48), "RefuelDrogueScript": ("RefuelDrogueData", 28),
    "ResizableWheelScript": ("ResizableWheelData", 77), "RocketPodScript": ("RocketPodData", 19),
    "RocketWeaponScript": ("RocketWeaponData", 20), "RotatorScript": ("RotatorData", 29),
    "SuspensionScript": ("SuspensionData", 24), "TargetingPodScript": ("TargetingPodData", 52),
    "TurboshaftScript": ("TurboshaftData", 114), "WingScript": ("WingData", 111),
}

# Each entry corresponds to an individually audited callsite. This intentionally
# does not reproduce source_line, even for declarations or one-line consumers.
RUNTIME_INPUTS = [
    ("bool", "part", "激活入口声明：非负整数1..8读取激活组，0或大于8由valueIfZero决定，其余走布尔getter。"),
    ("bool", "part", "激活字段未匹配整数分支时，使用同一部件上下文读取布尔输入。"),
    ("float", "optional_part", "轴入口声明：支持轴快捷名与FT；默认布尔低值-1，可选部件上下文，returnNull控制失败回退。"),
    ("float", "part", "轴快捷匹配之后在选定上下文编译float表达式，最终非有限结果按解析器规则处理。"),
    ("bool", "optional_part", "布尔入口声明：先匹配原生控制快捷项，再处理带部件上下文的布尔表达式。"),
    ("bool", "part", "布尔快捷匹配之后，使用部件ExpressionContext编译bool表达式。"),
    ("bool", "part", "阻拦钩ActivationGroup控制激活；1..8读组，0或大于8为false。"),
    ("bool", "part", "信标灯ActivationGroup控制激活；0或大于8为true。"),
    ("bool", "part", "信标灯Input作为布尔开关读取，不能按普通灯亮度float输入解释。"),
    ("float", "no_part", "座舱按钮先尝试匹配原生轴输入；没有部件FT上下文，失败返回null后进入自定义变量绑定路径。"),
    ("float", "part", "座舱声音的ActivationGroup除AlwaysOn/AlwaysOff和组号外作为float输入，强度按基础强度乘clamp01(1-input)计算。"),
    ("float", "no_part", "座舱开关先尝试原生轴名；没有部件FT上下文，失败返回null后进入自定义变量绑定路径。"),
    ("float", "wing_part", "控制面InputId在翼面部件上下文读取float，可访问Aileron与WingFlipped局部变量。"),
    ("bool", "wing_part", "控制面ActivationString使用翼面上下文；0或大于8按true处理。"),
    ("bool", "part", "分离器Group作为激活组或布尔表达式；0或大于8为false。"),
    ("float", "part", "仪表FaceInput驱动表盘旋转，后续倍率与反向按仪表配置应用。"),
    ("float", "part", "每个仪表指针的Input分别读取float，使用各自指针倍率和反向设置。"),
    ("bool", "part", "陀螺仪ActivationGroup决定激活，0或大于8为true。"),
    ("bool", "part", "InputController的ActivationGroup控制更新与保持；0或大于8为true。"),
    ("float", "part", "InputController的Input读取float，经Axis反转、分段Min/Max映射、Output反转产生Value；不自动限幅。"),
    ("string_or_float_template", "part", "标签建立动态文本源：无格式的花括号表达式求string，有格式时求float；状态子表达式与普通子表达式调度不同。"),
    ("bool", "part", "普通灯ActivationGroup控制激活，0或大于8为true。"),
    ("float", "part", "普通灯Input是float强度输入；原生布尔快捷输入低值为0，区别于默认-1轴入口。"),
    ("bool", "part", "磁铁ActivationGroup控制吸附激活，0或大于8为false。"),
    ("context_dependent", "mfd", "MFD建立独立动态表达式源，根对象craft/mfd，不自动包含普通craft裸变量；默认时间步长为1。"),
    ("bool", "part", "降落伞ActivationGroup控制部署条件，0或大于8为false。"),
    ("controller_reference", "part", "按字符串id查找已配置InputController的声明；该id本身不是FT表达式。"),
    ("controller_reference", "part", "按原生控制属性选取InputController的声明；属性选择器不是玩家FT文本。"),
    ("controller_reference", "part", "把原生控制属性名和默认控制委托交给控制器查找，沿用对应控制轴默认值。"),
    ("controller_reference", "part", "按id及默认控制委托查找控制器的重载声明，提供缺失控制器的回退。"),
    ("controller_reference", "part", "先按id查找部件已有控制器；缺失时使用调用方提供的默认控制委托。"),
    ("float_via_controller", "part", "脚踏按配置Input选择InputController；表达式位于所引用控制器的input字段。"),
    ("float_via_controller", "part", "差速器读取名为bias的控制器，驱动差速偏置。"),
    ("float_via_controller", "part", "变速箱读取名为shift的控制器，作为换挡控制输入。"),
    ("float_via_controller", "part", "发动机公共控制读取Throttle控制器，缺省采用原生油门轴。"),
    ("float_via_controller", "part", "发动机公共控制读取Pitch控制器，缺省采用原生俯仰轴。"),
    ("float_via_controller", "part", "发动机公共控制读取Roll控制器，缺省采用原生滚转轴。"),
    ("float_via_controller", "part", "发动机公共控制读取Yaw控制器，缺省采用原生偏航轴。"),
    ("float_via_controller", "part", "喷气发动机读取Thrust Reverse控制器，作为反推输入。"),
    ("float_via_controller", "part", "螺旋桨组件读取BladeAngle控制器，驱动桨叶角度。"),
    ("float_via_controller", "part", "螺旋桨组件读取ReverseThrust控制器，驱动反推。"),
    ("float", "no_part", "姿态控制喷嘴重新选择输入轴的入口之一，没有提供部件上下文；不能据此承诺任意FT可用。"),
    ("float", "no_part", "姿态控制喷嘴重新选择输入轴的第二入口，没有提供部件上下文；独立保留此调用位置。"),
    ("float", "no_part", "姿态控制喷嘴重新选择输入轴的第三入口，没有提供部件上下文；独立保留此调用位置。"),
    ("bool", "part", "姿态控制喷嘴ActivationGroup决定启用，0或大于8为true。"),
    ("float", "part", "姿态控制喷嘴初始化轴输入时传入部件上下文，支持该上下文的float表达式。"),
    ("bool", "part", "加油锥套ActivationString先处理空白/None为true，再走激活入口；0或大于8为false。"),
    ("controller_reference", "part", "旋转器按名称在控制器列表中查找的辅助方法声明，名称本身不执行FT。"),
    ("float_via_controller", "part", "旋转器InputX选择用于X轴的控制器。"),
    ("float_via_controller", "part", "旋转器InputY选择用于Y轴的控制器。"),
    ("float_via_controller", "part", "旋转器InputZ选择用于Z轴的控制器。"),
    ("bool", "part", "瞄准吊舱ActivationGroup控制启用，0或大于8为true。"),
    ("bool", "part", "部件输出Activator直接编译bool FT；整数1是真值，不是激活组1，组条件应写Activate1。"),
    ("bool", "part", "火炮首次读取激活状态时建立ActivationGroup getter并缓存；0或大于8为true。"),
    ("float", "part", "火炮FuseInput读取float引信输入；returnNull允许无有效输入时保留调用方回退行为。"),
    ("bool", "part", "诱饵投放器IsArmed按ActivationGroup建立并调用缓存激活getter；0或大于8为true。"),
    ("bool", "part", "爆炸武器基类缓存ActivationGroup激活getter；0或大于8为true。"),
    ("bool", "part", "机枪缓存ActivationGroup激活getter；0或大于8为true。"),
    ("bool", "part", "火箭巢缓存ActivationGroup激活getter；0或大于8为true。"),
    ("bool", "part", "火箭武器缓存ActivationGroup激活getter；0或大于8为true。"),
    ("float_via_controller", "part", "轮组读取Turn控制器，作为车轮转向输入。"),
    ("float_via_controller", "part", "轮组读取Brake控制器，作为车轮制动输入。"),
    ("float", "no_part", "XR控制基类先把InputName匹配到原生轴；无部件上下文且失败返回null，随后可走自定义变量绑定。"),
    ("float", "craft", "Setter Expression在载具上下文编译float值，按Setter列表顺序写入目标变量。"),
    ("bool", "craft", "Setter Activator直接编译bool FT；空值默认true，数字不代表激活组编号。"),
    ("float", "no_part", "场景InputRequirement从玩家载具按InputId取轴并调用，没有提供部件上下文；不是通用部件FT入口。"),
]

MFD_MEANINGS = {
    "CraftControlsProxy.GetActivationState": "按给定激活组编号读取组状态；参数是int，FT数字到int的适配未验证。",
    "CraftControlsProxy.OverrideInput": "创建或复用该名称的原生RawOverride，设为激活并写入value；有控制副作用，同轴有效覆盖按平均值合成。",
    "CraftControlsProxy.ReleaseInput": "使此前由该代理建立的同名原生输入覆盖失活；不存在时不创建覆盖。",
    "CraftControlsProxy.ToggleActivationGroup": "将传入组号减1后切换原生激活组；有控制副作用，边界与FT调用兼容性未验证。",
    "CraftProxy.AngularVelocity": "读取载具角速度向量；返回Vector3对象，不是三个已注册的float裸变量。",
    "CraftProxy.Controls": "取得该载具的控制代理，可继续访问控制轴、按钮和覆盖操作。",
    "CraftProxy.MainCockpit": "取得主驾驶舱PartScript对象；对象成员在FT中的完整可调用域未验证。",
    "CraftProxy.Targeting": "取得该载具的目标系统代理，用于目标、武器选择及瞄准吊舱信息。",
    "CraftProxy.Time": "读取本次关卡加载以来的Unity时间，单位秒；与普通FT中从载具Initialize起算的Time不同。",
    "CraftProxy.PitchRate": "把载具角速度变换到主驾驶舱局部坐标，取x分量并转为度每秒；此代理getter没有额外的非Flight归零分支。",
    "CraftProxy.RollRate": "把载具角速度变换到主驾驶舱局部坐标，取z分量并转为度每秒；此代理getter没有额外的非Flight归零分支。",
    "CraftProxy.YawRate": "把载具角速度变换到主驾驶舱局部坐标，取y分量并转为度每秒；此代理getter没有额外的非Flight归零分支。",
    "MfdProxy.RootWidget": "取得当前MFD程序根Widget的代理，作为页面控件遍历起点。",
    "MfdProxy.SelectPage": "按页面id切换当前MFD页面；会改变显示状态。",
    "TargetingSystemProxy.CountermeasureAmmo": "读取目标系统汇总的诱饵剩余弹药，返回int。",
    "TargetingSystemProxy.Mode": "读取或设置目标系统模式枚举，写入会改变目标匹配模式。",
    "TargetingSystemProxy.SelectedWeapon": "取得当前选择武器系统的代理；无选择时的空对象行为需调用方处理。",
    "TargetingSystemProxy.Target": "取得当前跟踪目标的代理；与普通FT的目标是否匹配模式布尔值不同。",
    "TargetingSystemProxy.TgpActive": "读取瞄准吊舱激活状态；无吊舱返回false。",
    "TargetingSystemProxy.TgpDistance": "读取瞄准吊舱跟踪目标距离；吊舱或目标缺失返回0。",
    "TargetingSystemProxy.GetWeaponSystem": "按从1开始的index读取当前模式武器列表；超出上界返回空，源码未保护负索引，不保证非法索引安全。",
    "TargetingSystemProxy.NextTarget": "切换到下一个目标，有目标选择副作用。",
    "TargetingSystemProxy.PreviousTarget": "切换到上一个目标，有目标选择副作用。",
    "TargetingSystemProxy.SelectWeapon": "按从1开始的index查找武器后选择；查找为空时向原生选择逻辑传空。",
    "TargetProxy.Distance": "读取此跟踪目标的距离，单位按底层跟踪系统，米为推断。",
    "TargetProxy.Name": "读取此跟踪目标对应对象的名称字符串。",
    "WeaponSystemProxy.Ammo": "读取此武器系统的剩余弹药数，返回int。",
    "WeaponSystemProxy.Name": "读取此武器系统WeaponPartName显示名称，可与ammo的名称匹配逻辑对照。",
    "WeaponSystemProxy.Selected": "判断此武器系统是否就是目标系统当前选择的武器。",
    "WeaponSystemProxy.WeaponSystem": "取得底层武器系统对象；暴露对象不保证其任意成员可在FT内使用。",
    "WidgetProxy.Data": "读写此控件关联的Data字符串。",
    "WidgetProxy.Flagged": "读写此控件的Flagged布尔标记。",
    "WidgetProxy.Id": "读取此控件的标识字符串，用于查找与页面结构定位。",
    "WidgetProxy.IsDestroyed": "判断该代理持有的底层控件是否已为空。",
    "WidgetProxy.Parent": "取得父控件代理，用于向上遍历控件层次。",
    "WidgetProxy.Visible": "读写此控件的可见性；写入会改变显示。",
    "WidgetProxy.AddClass": "给控件添加指定样式类，并返回底层添加操作的bool结果。",
    "WidgetProxy.AddWidget": "把传入代理对应的控件加入此控件，改变控件树。",
    "WidgetProxy.Destroy": "销毁此控件，属于有副作用的UI操作。",
    "WidgetProxy.FindParentWidget": "按id在祖先方向查找控件并返回代理。",
    "WidgetProxy.FindWidget": "按id调用此控件的查找逻辑并包装结果；具体查找范围由底层实现决定。",
    "WidgetProxy.GetChild": "用从0开始的列表索引取得直接子控件；没有在代理中额外保护越界。",
    "WidgetProxy.GetChildCount": "返回此控件直接子控件列表的数量，类型int。",
    "WidgetProxy.HasClass": "判断此控件是否具有指定样式类。",
    "WidgetProxy.RemoveClass": "移除此控件的指定样式类，并返回底层移除操作的bool结果。",
    "WidgetProxy.SetIndex": "调用底层控件的SetIndex改变排序位置；参数int及边界需另行验证。",
    "WidgetProxy.SetStyle": "仅当指定样式名的现值与value不同时写入新样式字符串。",
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def game_relative(path: str) -> str | None:
    normalized = path.replace("\\", "/")
    marker = "/Game/"
    if marker not in normalized:
        return None
    return normalized.split(marker, 1)[1]


def parameter_unit(function: str, name: str) -> str:
    if name in ("format", "weapon"):
        return "string"
    if function in ("sin", "cos", "tan", "deltaangle"):
        return "deg"
    if function == "lerpangle":
        return "ratio" if name == "t" else "deg"
    if function == "smooth" and name == "maxRate":
        return "value_unit/s (craft); value_unit/step (default context)"
    if function == "PID":
        return {"target": "input_unit", "current": "input_unit", "p": "output_unit/input_unit",
                "i": "output_unit/(input_unit*s)", "d": "output_unit*s/input_unit"}[name]
    if name in ("t", "power", "base") and function not in ("pingpong", "repeat"):
        return "dimensionless"
    if function in ("exp", "log", "log10", "asin", "acos", "atan", "sign", "clamp01"):
        return "dimensionless"
    return "caller_defined; compatible units required"


def return_unit(function: str) -> str:
    if function in ("asin", "acos", "atan", "atan2", "deltaangle", "lerpangle"):
        return "deg"
    if function in ("sin", "cos", "tan", "exp", "log", "log10", "sign", "clamp01", "inverselerp"):
        return "dimensionless"
    return {"sum": "input_unit*s (craft)", "rate": "input_unit/s (craft)",
            "PID": "output_unit set by gains", "ammo": "count", "format": "string",
            "sqrt": "sqrt(input_unit)", "pow": "depends on exponent"}.get(function, "same as value/endpoints")


def type_graph(ast_path: Path):
    """Resolve actual qualified C# bases using frozen AST and checked sources.

    No Script/Data suffix inference or global short-name union is permitted.
    Only namespace scope and explicit using directives resolve short names.
    """
    raw = ast_path.read_bytes()
    if digest(raw) != SOURCE_AST_SHA256:
        raise ValueError("Source AST changed: review inheritance before regenerating knowledge")
    ast = json.loads(raw)
    classes = {row['qualifiedName']: row for row in ast['classes']}
    files = {game_relative(row['path']): row['sha256'] for row in ast['files']}
    texts, verified = {}, {}

    def checked_text(qualified):
        row = classes[qualified]
        relative = game_relative(row['path'])
        if relative is None or relative not in files:
            raise ValueError('Type has no frozen current-Game source: ' + qualified)
        if relative not in texts:
            content = Path(row['path']).read_bytes()
            if digest(content) != files[relative]:
                raise ValueError('Type source hash changed: ' + relative)
            texts[relative] = content.decode('utf-8-sig')
            verified[relative] = files[relative]
        return texts[relative]

    def resolve(name, context):
        name = re.split(r'[<(]', name.replace('global::', '').strip(), maxsplit=1)[0].strip()
        if name in classes:
            return name
        namespace = context.rsplit('.', 1)[0]
        scopes = namespace.split('.')
        for end in range(len(scopes), 0, -1):
            candidate = '.'.join(scopes[:end]) + '.' + name
            if candidate in classes:
                return candidate
        using = re.findall(r'^\s*using\s+([A-Za-z_][\w.]*)\s*;', checked_text(context), re.MULTILINE)
        candidates = sorted({value + '.' + name for value in using if value + '.' + name in classes})
        if len(candidates) > 1:
            raise ValueError('Ambiguous type reference: ' + context + ' -> ' + name)
        return candidates[0] if candidates else None

    bases = {}
    def ancestors(qualified, active=()):
        if qualified in active:
            raise ValueError('Cyclic source inheritance: ' + qualified)
        checked_text(qualified)
        if qualified not in bases:
            bases[qualified] = [resolved for raw_base in classes[qualified]['baseTypes'] if (resolved := resolve(raw_base, qualified))]
        result = {qualified: [qualified]}
        for base in bases[qualified]:
            for ancestor, chain in ancestors(base, (*active, qualified)).items():
                candidate = [qualified, *chain]
                if ancestor not in result or len(candidate) < len(result[ancestor]):
                    result[ancestor] = candidate
        return result

    def reference(qualified):
        row = classes[qualified]
        checked_text(qualified)
        return {'path': game_relative(row['path']), 'line': row['line'], 'endLine': row['line'],
                'sha256': files[game_relative(row['path'])], 'grade': 'B_SOURCE'}

    def at_path(name, path):
        matches = [key for key, row in classes.items() if row['name'] == name and game_relative(row['path']) == path]
        if len(matches) != 1:
            raise ValueError('Cannot uniquely resolve source type: ' + name + ' at ' + path)
        checked_text(matches[0])
        return matches[0]
    return classes, resolve, ancestors, reference, at_path, verified


def build(inventory_path: Path, parts_path: Path | None = None, source_ast_path: Path | None = None) -> dict:
    raw = inventory_path.read_bytes()
    if digest(raw) != INVENTORY_SHA256:
        raise ValueError("FT inventory changed: review source and curated semantics before updating the frozen SHA256")
    data = json.loads(raw.decode("utf-8"))
    parts_path = parts_path or Path(__file__).resolve().parents[1] / "knowledge/v077/parts.json"
    parts = json.loads(parts_path.read_bytes())
    if parts["source"]["sourceInventorySha256"] != SHARED_INVENTORY_SHA256:
        raise ValueError("Part mapping inventory does not match the frozen shared source")
    source_ast_path = source_ast_path or inventory_path.parent.parent / 'xml-source/source-ast-index.json'
    classes, resolve_type, ancestors, type_reference, type_at_path, verified_types = type_graph(source_ast_path)
    class_parts, mapping_chains = {}, {}
    for part in parts["collections"]["parts"]:
        for mapping in part.get("modifierMappings", []):
            qualified = mapping['classQualifiedName']
            if qualified not in classes:
                raise ValueError('Part modifier type absent from frozen AST: ' + qualified)
            for ancestor, chain in ancestors(qualified).items():
                class_parts.setdefault(ancestor, set()).add(part['id'])
                key = (ancestor, part['id'])
                if key not in mapping_chains or len(chain) < len(mapping_chains[key]):
                    mapping_chains[key] = chain
    for field in parts["collections"]["fields"]:
        declaring = field.get("declaringClass", "")
        if declaring in classes and field.get("partType"):
            class_parts.setdefault(declaring, set()).add(field["partType"])
    mapping_payload = {k: sorted(v) for k, v in sorted(class_parts.items())}
    hashes = {game_relative(x["path"]): x["sha256"] for x in data["source_manifest"] if game_relative(x["path"])}

    def evidence(items: list) -> list:
        result = []
        for item in items:
            path = game_relative(item["path"])
            if path is None:
                continue  # Private native/export/help snapshots are audit-only.
            if path not in hashes:
                raise ValueError("Evidence file has no frozen hash: " + path)
            ref = {"path": path, "line": item["line"],
                   "endLine": item.get("end_line", item["line"]),
                   "sha256": hashes[path], "grade": item["grade"]}
            if ref not in result:
                result.append(ref)
        return result

    def record(identifier: str, title: str, summary: str, refs: list, **fields) -> dict:
        return {"id": identifier, "title": title, "summary": summary,
                "evidence": evidence(refs), "runtimeEvaluated": False, **fields}

    collections = {key: [] for key in EXPECTED_COUNTS}
    rules_by_id = {v["id"]: v for v in data["rules"]}
    for item in data["rules"]:
        collections["rules"].append(record(item["id"], item["title_zh"], item["semantics_zh"], item["evidence"],
                                             grade="B_SOURCE"))
    rules = {v["id"]: v for v in collections["rules"]}
    # Keep the twenty-one original IDs (S/T/L/B/I families) and their denominator.
    for item in data["functions"]:
        name = item["name"]
        semantics = {p["semantic_name"]: p for p in item.get("parameter_semantics", [])}
        parameters = [{**p, "nativeName": semantics.get(p["name"], {}).get("name", p["name"]),
                       "summary": semantics.get(p["name"], {}).get("meaning_zh", ""),
                       "unit": parameter_unit(name, p["name"]), "optional": False}
                      for p in item["parameters"]]
        item_record = record(name, name, item["semantics_zh"], item["evidence"], name=name,
                             signature=item["signature"], parameters=parameters, parameterCount=len(parameters),
                             returnType=item["return_type"], returnUnit=return_unit(name),
                             scope=item["scope"], stateful=item["stateful"], nativeTarget=item["native_target"],
                             grade=item["semantic_grade"], nativeContextMatched=True,
                             example={"expression": FUNCTION_EXAMPLES[name], "status": "source-derived; not compiled or evaluated"},
                             rules=["S02", "T01", "T03"])
        if item["stateful"]:
            item_record["lifecycle"] = {"summary": rules["L01"]["summary"],
                "initialState": {"sum": "累加器0；首调用也累计value*dt。", "rate": "未采样；首调用记住输入并返回0。",
                                 "PID": "积分0且尚无上次current；首调用D项为0。", "smooth": "未采样；首调用直接采用value。"}[name],
                "timeStep": "craft: Unity Time.deltaTime，单位秒；无显式GetDeltaTime的默认Context为1。",
                "reset": "没有reset参数；重新编译会新建每个调用token的状态，跨保存恢复unknown。",
                "evidence": rules["L01"]["evidence"]}
            item_record["rules"] += ["L01", "L02", "T02"]
        item_record["boundaries"] = ("Unity Mathf函数体不在当前源码树；半数舍入、零点符号及异常输入边界没有运行验证。"
                                      if item["semantic_grade"] == "C_INFERENCE_EXTERNAL_BODY_UNAVAILABLE"
                                      else "源码说明与签名核对完成；示例未编译/求值，非法输入或实际调度效果需独立验证。")
        collections["functions"].append(item_record)

    constant_summaries = {"true": "布尔真常量；转float时为1。", "false": "布尔假常量；转float时为-1，不是0。",
                          "pi": "当前原生context中的单精度圆周率值。", "e": "当前原生context的e为0；源码注册的是1的自然对数，没有按数学常数e修正游戏。"}
    for item in data["constants"]:
        collections["constants"].append(record(item["name"], item["name"], constant_summaries[item["name"]],
            item["evidence"] + (rules_by_id["T01"]["evidence"] if item["type"] == "bool" else []),
            type=item["type"], value=item["native_value"], scope="default_context", nativeContextMatched=True,
            grade="A_NATIVE_CONTEXT_AND_B_SOURCE", rules=["T01"]))

    for item in data["variables"]:
        summary = item["semantics_zh"].replace("，详见getter", "，返回值受射线结果影响")
        if item["name"] == "VerticalG":
            summary = "载具加速度减重力后，投影到主驾驶舱上方向，再除以9.81，保留投影符号。"
        elif item["name"] == "AltitudeAgl":
            summary = "从有向重心位置向下无限射线求地面间距；位置未变时复用缓存，未命中时回退海拔Altitude。"
        local = item["scope"] == "control_surface_axis_part_context_only"
        custom = item["scope"] == "default_user_variable"
        unit = item["unit"]
        if unit == "normalized input / bool":
            unit = "boolean" if item["type"] == "bool" else "0_or_1" if item["name"] == "LandingGear" else "normalized_input"
        collections["variables"].append(record(item["name"], item["name"], summary, item["evidence"],
            type=item["type"], scope=item["scope"], unit=unit,
            availability="仅控制面专用轴部件上下文" if local else "载具默认自定义变量" if custom else "普通载具FT上下文",
            refresh="VariableSystem写入阶段更新；无写入保持旧值。" if custom else "按getter在求值时读取当前状态；底层更新与调用频率由运行消费者决定。",
            writable=custom, nativeContextMatched=not local, grade="B_SOURCE", rules=["B01", "B02", "B03"] if custom else ["L02", "I02"]))

    for item in data["ui_funky_opt_ins"]:
        summary = item["evaluation_status"]
        is_ft = not (summary.startswith("NOT FT") or item["class"] == "PosedGripData")
        if summary.startswith("NOT FT"):
            summary = "不是FT入口：字段类型为DetacherDirection枚举，UI属性类会禁用Funky选项；不能用表达式替代枚举值。"
        expected_type = "not_ft" if not is_ft else "float" if ("float" in summary) else "bool"
        collections["inputs"].append(record("ui:" + item["class"] + "." + item["member"],
            item["class"] + " · " + item["native_label"], summary, item["evidence"], kind="ui",
            className=item["class"], member=item["member"], declaredType=item["type"], expectedType=expected_type,
            acceptsFunkyExpression=is_ft, grade=item.get("runtime_entry_confirmation", "B_SOURCE"), rules=["I01", "I02", "I03"]))
    if len(RUNTIME_INPUTS) != len(data["runtime_input_callsites"]):
        raise ValueError("Runtime input curation is not exhaustive")
    for item, (expected_type, scope, summary) in zip(data["runtime_input_callsites"], RUNTIME_INPUTS):
        ref = item["evidence"][0]
        identifier = "runtime:" + item["class"] + ":" + str(ref["line"])
        collections["inputs"].append(record(identifier, item["class"] + " · 输入入口 " + str(ref["line"]), summary,
            item["evidence"], kind="runtime", className=item["class"], expectedType=expected_type,
            scope=scope, classification=item["classification"], grade="B_SOURCE",
            rules=["I04"] if scope == "mfd" else ["I01", "I02", "I03", "L02"]))

    variable_map = {v["id"]: v for v in collections["variables"]}
    for item in data["part_output_definitions"]:
        cls, member = item["class"], item["member"]
        summary, unit = output_semantics(item)
        collections["outputs"].append(record(cls + "." + member, cls + " · " + item["native_display_name"], summary,
            item["evidence"], className=cls, member=member, outputId=item["output_id"],
            displayName=item["native_display_name"], type=item["type"], unit=unit,
            scope="part_output_binding", defaultVariable=item["default_variable"], defaultPriority=item["default_priority"],
            binding={"fields": ["id", "variable", "priority", "activator"], "idMeaning": "部件Modifier属性名；显示名称不能代替id。",
                     "target": "必须绑定已声明自定义变量才进入普通FT上下文；有默认目标时沿用该默认绑定。",
                     "activatorType": "bool", "activation": "空Activator默认true；整数1为真，激活组1需写Activate1。",
                     "priority": rules["B02"]["summary"], "order": rules["B01"]["summary"],
                     "evidence": rules["B05"]["evidence"] + rules["B01"]["evidence"] + rules["B02"]["evidence"]},
            grade="B_SOURCE", rules=["B01", "B02", "B03", "B05"]))

    for item in data["mfd_proxy_members"]:
        cls, member = item["class"], item["member"]
        identifier = cls + "." + member
        if identifier in MFD_MEANINGS:
            summary = MFD_MEANINGS[identifier]
        elif cls == "CraftProxy" and member in variable_map:
            summary = "MFD载具代理：" + variable_map[member]["summary"]
        elif cls == "CraftControlsProxy" and item["parameters"] is None:
            controls = {"LandingGearDown": "起落架放下状态", "Vtol": "垂直起降轴", "TargetingPodSlewLeftRight": "瞄准吊舱左右转动轴",
                        "TargetingPodSlewUpDown": "瞄准吊舱上下转动轴", "TargetingPodZoom": "瞄准吊舱缩放轴"}
            summary = "读写原生控制的" + controls.get(member, member) + "当前值；写入会影响控制状态。"
        else:
            raise ValueError("Uncurated MFD member " + identifier)
        source = item["source"]
        collections["mfd"].append(record(identifier, identifier, summary, item["evidence"], className=cls,
            member=member, type=item["type"], parameters=item["parameters"], scope="mfd_context_only",
            access="method" if item["parameters"] is not None else "read_write" if re.search(r"\bset\b", source) else "read_only",
            compileStatus="unknown; declaration exposure does not prove FT compile success",
            typeLimit="FT无通用float到int隐式转换；int/void/对象及继承成员完整适用性未验证。",
            grade="B_SOURCE", rules=["I04"], unknowns=["U05"]))

    for item in data["examples"]:
        expr = item["expression"]
        collections["examples"].append(record("example:" + digest(expr.encode("utf-8"))[:16], expr,
            "源码推导示例：" + item["expected_source_result"] + "；没有运行求值。", item["evidence"],
            expression=expr, expectedSourceResult=item["expected_source_result"], kind=item["kind"],
            compileStatus="not_performed", evaluationStatus="not_performed", grade="C_SOURCE_DERIVED"))
    for item in data["remaining_ambiguities"]:
        summary = item["unknown"].replace("索引保留完整getter", "审计保留完整getter，产品仅保留派生说明和源码引用")
        collections["unknowns"].append(record(item["id"], item["topic"], summary, [],
            nextEvidence=item["next_evidence"], grade="UNKNOWN", status="unresolved"))

    historical = []
    for item in data["official_help_comparison"]:
        refs = evidence(item["evidence"])
        if not refs:
            refs = [x for v in collections["functions"] + collections["variables"]
                    if v["id"] in ["format", "Flaps", "GearDown", "ParkingBrake", "Rpm1", "RotorRPM", "TargetLocked", "TargetLocking", "Aileron", "WingFlipped"]
                    for x in v["evidence"]]
        historical.append({"topic": item["topic"], "historicalHelp": item["help"], "current": item["current"],
                           "status": item["status"], "evidence": refs,
                           "historicalGrade": "D_OFFICIAL_HELP", "runtimeEvaluated": False})
    rules["S04"]["historicalDifferences"] = [v for v in historical if v["topic"] == "equality"]
    rules["I04"]["historicalDifferences"] = [v for v in historical if v["topic"] == "Time lifecycle"]
    rules["B03"]["historicalDifferences"] = [v for v in historical if v["topic"] in ["selected weapon", "new inventory"]]
    next(v for v in collections["constants"] if v["id"] == "e")["historicalDifferences"] = [v for v in historical if v["topic"] == "e"]
    rules["B05"]["workedExample"] = {
        "summary": "把主旋翼输出经变量和Setter送到另一控制器；以下是配置示意，未运行，也不代表调速闭环已稳定。",
        "steps": [
            {"output": "HeliMainRotorScript.RotorRPM", "binding": {"id": "RotorRPM", "variable": "RotorRPM", "priority": 10, "activator": "true"}},
            {"setter": {"variable": "RotorCommand", "function": "Activate1 ? clamp(RotorRPM / 1000,0,1) : Throttle", "priority": 20, "activator": "true"}},
            {"inputController": {"input": "RotorCommand", "activationGroup": "0", "min": -1, "max": 1, "zeroOnDeactivate": True}},
        ],
        "expected": "在VariableSystem自己的写入阶段先读输出再按列表执行Setter；若当次RotorRPM为500且Activate1为true，源码推导RotorCommand为0.5。控制器与VariableSystem的全局相对顺序未测，可能读到上一阶段值。",
        "manualBypass": "Activate1为false时选择Throttle；调试可先把Setter函数改为常量0，再逐段核对绑定id、变量是否声明、Activator与优先级。",
        "evidence": rules["B01"]["evidence"] + rules["B02"]["evidence"] + rules["I01"]["evidence"],
        "runtimeEvaluated": False,
    }
    native_bindings = [{"templateId": v["template_id"], "templateName": v["template_name"],
                       "partType": v["part_type"], "inputControllers": v["input_controllers"], "outputs": v["outputs"],
                       "grade": "A_NATIVE_SNAPSHOT_METADATA", "runtimeEvaluated": False}
                      for v in data["catalog_builtin_bindings"]]
    for row in collections["inputs"] + collections["outputs"]:
        cls = row["className"]
        data_class = cls if row.get("kind") == "ui" else SCRIPT_DATA.get(cls, (None, None))[0]
        source_type = type_at_path(cls, row['evidence'][0]['path'])
        data_qualified = source_type if row.get('kind') == 'ui' else resolve_type(data_class, source_type) if data_class else None
        row['classQualifiedName'] = source_type
        row['dataClassQualifiedName'] = data_qualified
        row["partTypes"] = sorted(class_parts.get(data_qualified, ()))
        row["partTypeMappingStatus"] = "source_typed_data_and_part_field_join" if row["partTypes"] else "unavailable_no_confirmed_part_join"
        row["partTypeMappingScope"] = "冻结内置部件资料；不代表当前实例存在、字段可写或运行功能已通过。"
        if cls in SCRIPT_DATA:
            line = SCRIPT_DATA[cls][1]
            ref = row["evidence"][0]
            row["partTypeMappingEvidence"] = [{**ref, "line": line, "endLine": line, "grade": "B_SOURCE"}]
            row["dataClass"] = data_class
        row['partTypeInheritance'] = [{'partType': part, 'classChain': mapping_chains[(data_qualified, part)],
                                       'evidence': [type_reference(name) for name in mapping_chains[(data_qualified, part)]]}
                                      for part in row['partTypes'] if (data_qualified, part) in mapping_chains and len(mapping_chains[(data_qualified, part)]) > 1]
        if cls == "EngineCommon":
            row["partTypes"] = sorted(class_parts.get("Assets.Scripts.Craft.Parts.Modifiers.Propulsion.Jet.JetEngineData", ()))
            row["partTypeMappingStatus"] = "source_enginecommon_owner_join"
            path = next(p for p in hashes if p.endswith("/JetEngineScript.cs"))
            row["partTypeMappingEvidence"] = [{"path": path, "line": 279, "endLine": 279, "sha256": hashes[path], "grade": "B_SOURCE"}]
        matches = []
        for binding in native_bindings:
            if binding["partType"] not in row["partTypes"]:
                continue
            if "outputId" in row:
                groups = [g for g in binding["outputs"] if any(d["id"] == row["outputId"] for d in g["definitions"])]
                if groups:
                    matches.append({k: binding[k] for k in ("templateId", "templateName", "partType", "grade")} | {"outputs": groups})
            elif binding["inputControllers"]:
                matches.append({k: binding[k] for k in ("templateId", "templateName", "partType", "grade")} |
                               {"inputControllers": binding["inputControllers"], "relationship": "同部件默认控制器；不表示本入口使用每一个控制器。"})
        row["matchingNativeBindings"] = matches
    rules["B05"]["nativeCatalogBindings"] = native_bindings
    for values in collections.values():
        values.sort(key=lambda v: v["id"])
    result = {
        "schemaVersion": "sp2model.knowledge/1",
        "source": {"gameVersion": "0.7.9.104", "steamBuildId": "25840865", "xmlVersion": 26,
                   "gameAssemblySha256": GAME_SHA256, "sourceInventorySha256": SHARED_INVENTORY_SHA256,
                   "ftInventorySha256": INVENTORY_SHA256,
                   "typeAstSha256": SOURCE_AST_SHA256,
                   "checkedTypeSourceCount": len(verified_types),
                   "partClassMappingSha256": digest(json.dumps(mapping_payload, sort_keys=True, ensure_ascii=False).encode("utf-8")),
                   "generatorVersion": "funky-077/2", "toolVersion": "0.7.7",
                   "evidencePathBase": "Game", "runtimeEvaluationPerformed": False,
                   "nativeContextComparison": {"functions": 35, "variables": 53, "differences": 0,
                                               "status": "read-only metadata comparison in frozen audit; no expression evaluation"}},
        "collections": collections,
        "officialHelpComparison": historical,
        "catalogBindings": native_bindings,
        "coverage": {"collections": EXPECTED_COUNTS, "ordinaryFunctions": 31, "statefulFunctions": 4,
                     "contextVariables": 53, "partLocalVariables": 2, "uiInputOptIns": 22,
                     "runtimeInputCallsitesIncludingDeclarations": 66, "builtinTemplateScan": 160,
                     "builtinPartBindings": 118, "sourceManifestFiles": len(hashes),
                     "officialHistoricalDifferences": 5, "unresolvedTopics": 8,
                     "inputsWithCurrentPartTypeJoin": sum(bool(r["partTypes"]) for r in collections["inputs"]),
                     "outputsWithCurrentPartTypeJoin": sum(bool(r["partTypes"]) for r in collections["outputs"]),
                     "denominator": "冻结源码声明与已加载内置目录；输入包含方法声明与非FT候选，不等于88种可执行FT字段。118为带输入/输出的内置part实例，不是独立零件型号。",
                     "excluded": "玩家子装配、存档、运行副本、原始快照及反编译函数体未进入发布知识。"},
        "limitations": ["所有表达式示例均为源码推导；未执行FT编译、表达式求值、飞行遥测、控制闭环或多人同步验收。",
                        "Unity Mathf外部函数体缺失，函数注册与原生context签名匹配不证明边界行为。",
                        "MFD为独立context；75个显式公开成员不等于75个已验证可调用FT表达式。",
                        "未验证全局调度相对顺序、暂停/远端条件、状态跨存档恢复与额外DLC/模组资产域。",
                        "源码证据仅保留Game相对路径、行号、文件哈希和等级；原生及历史网页私有快照不随产品分发。"],
    }
    validate(result)
    return result


def output_semantics(item: dict) -> tuple[str, str]:
    cls, member = item["class"], item["member"]
    summary = item["semantics_zh"]
    unit = "unknown; bottom-level unit not established by this source audit"
    if cls == "CameraVantageScript":
        if member == "Active":
            return "此相机被选中时输出1，否则0；是显式状态数值，不采用FT布尔false转-1规则。", "0_or_1"
        axes = {"LookPitch": "旋转x", "LookYaw": "旋转y", "LookRoll": "旋转z", "PosX": "位置偏移x", "PosY": "位置偏移y", "PosZ": "位置偏移z"}
        return "读取该相机视图的" + axes[member] + "分量；参考坐标、单位和量程未从此getter闭合。", unit
    if cls == "CockpitScript":
        if member.startswith("Pos"):
            return "该驾驶舱绝对世界位置的" + member[-1].lower() + "分量，在UpdateOutputs刷新；y未减海平面，不能当作全局Altitude。", "world_distance (m inferred)"
        summaries = {"Heading": "该驾驶舱朝向的水平atan2(x,z)转度再取%360，可能为负。", "PitchAngle": "该驾驶舱forward.y反正弦转度，再取相对0的最短角差。",
                     "RollAngle": "该驾驶舱欧拉角z相对0的最短角差。", "PitchRate": "该驾驶舱局部角速度x分量转为度每秒。",
                     "RollRate": "该驾驶舱局部角速度z分量转为度每秒。", "YawRate": "该驾驶舱局部角速度y分量转为度每秒。",
                     "Speed": "该驾驶舱所在位置的刚体点速度模长；不是固定读取主驾驶舱速度。"}
        return summaries[member], "m/s (inferred)" if member == "Speed" else "deg/s (inferred)" if member.endswith("Rate") else "deg"
    if member in ("Offroad", "GroundedOutput", "VariableFired"):
        label = {"Offroad": "处于越野地面状态", "GroundedOutput": "车轮接地", "VariableFired": "该武器已发射"}[member]
        return label + "时输出1，否则0；是显式状态数值，不采用FT布尔false转-1规则。", "0_or_1"
    if member in ("FSlip", "HSlip"):
        return "读取该轮控制器的" + ("纵向" if member == "FSlip" else "横向") + "滑移；未额外转换，精确单位与缩放unknown。", unit
    if member in ("RpmAbs", "RotorRPM", "RPM", "ReportedRpm", "EngineRpm"):
        return summary.replace("保持底层符号/缺失回退", "保持底层符号；Powertrain链缺失的EngineRpm回退0"), "rpm (source naming)"
    if cls == "EngineScript" and member == "Thrust":
        return "发动机脚本维护的推力输出；属性声明本身未建立所有发动机实现的单位/缩放和刷新细节。", unit
    if cls == "PropellerAssemblyScript" and member == "PropellerThrust":
        return "升力向量沿推力轴的投影除以0.01，保留投影符号；最终SI单位未独立验证。", "native_force / 0.01; SI unknown"
    if cls == "PropellerAssemblyScript" and member == "PropellerTorque":
        return "螺旋桨阻力矩除以0.01；扭矩SI单位与符号约定未独立验证。", "native_torque / 0.01; SI unknown"
    if cls == "WingScript":
        return ("机翼有符号升力幅值" if member == "LiftMag" else "机翼阻力幅值") + "除以0.01；不能从显示名称推定全部单位约定。", "native_force / 0.01; SI unknown"
    explicit = {
        "GearLegScript.Extension": ("起落架动画进度Percent；动画对象缺失时输出0。", "ratio (Percent)"),
        "JTransmissionScript.Gear": ("读取当前挡位编号并转float；变速箱不存在时0，挡位编号含义由传动系统决定。", "gear_index"),
        "JTransmissionScript.GearRatio": ("读取当前挡位传动比；变速箱不存在时0。", "ratio"),
        "JTransmissionScript.InputTorque": ("读取变速箱输入扭矩；不存在时0，没有额外单位转换。", unit),
        "JTransmissionScript.OutputTorque": ("读取变速箱输出扭矩；不存在时0，没有额外单位转换。", unit),
        "JEngineScript.OutputTorque": ("读取动力系统发动机的输出扭矩；动力链缺失时0，没有额外单位转换。", unit),
        "TurboshaftScript.OutputTorque": ("读取上次生成的涡轴发动机扭矩缓存；本getter没有额外单位转换。", unit),
        "TurboshaftScript.Spool": ("读取涡轴发动机内部spool状态缓存；精确归一化范围未由getter证明。", unit),
        "SuspensionScript.CurrOffset": ("悬架当前点在底点局部坐标系中的y位置。", "local_distance (m inferred)"),
    }
    if cls + "." + member in explicit:
        return explicit[cls + "." + member]
    if member in ("BodyAngle", "PropellerPitchDegrees"):
        unit = "deg"
    elif member in ("N1", "N2", "TorqueRatio"):
        unit = "ratio"
    elif member == "ammo":
        unit = "count"
    return summary, unit


def validate(data: dict) -> None:
    for key, count in EXPECTED_COUNTS.items():
        rows = data["collections"][key]
        if len(rows) != count or len({r["id"] for r in rows}) != count:
            raise ValueError("Incomplete or duplicate collection " + key)
        for row in rows:
            if any(not isinstance(row.get(k), str) or not row[k].strip() for k in ("id", "title", "summary")):
                raise ValueError("Incomplete description " + str(row.get("id")))
    blob = json.dumps(data, ensure_ascii=False)
    if re.search(r"[A-Za-z]:[\\/]", blob) or "source_line" in blob or "public float " in blob or "private float " in blob:
        raise ValueError("Private path or decompiled code leaked into product")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True, help="Frozen funky-trees-index.json (read-only)")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "knowledge/v077/funky.json")
    parser.add_argument("--parts", type=Path, help="Generated parts.json used for exact typed-Data to partType joins")
    parser.add_argument("--source-ast", type=Path, help="Frozen source AST used for qualified inheritance closure; defaults beside the audit inventory")
    parser.add_argument("--check", action="store_true", help="Verify checked-in output without changing it")
    args = parser.parse_args()
    product = build(args.inventory, args.parts, args.source_ast)
    serialized = (json.dumps(product, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    if args.check:
        if args.output.read_bytes() != serialized:
            raise SystemExit("FT knowledge is stale; regenerate after reviewing the difference")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(serialized)
    print(json.dumps({"collections": EXPECTED_COUNTS, "bytes": len(serialized), "sha256": digest(serialized)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
