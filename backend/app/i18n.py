"""Server messages in Khmer and Chinese (one central list).

The code always raises errors in English. An exception handler (main.py) looks at
the request's Accept-Language header (sent by the LAGOM app in the user's chosen
language) and translates the message with this table. Unknown messages stay English.
Messages that contain a name (e.g. "Fried Rice is sold out right now.") are matched
with a pattern and translated without the name; the app shows which item it is.
"""
import re

LANGS = ("en", "km", "zh")

# English -> (Khmer, Chinese)
MESSAGES: dict[str, tuple[str, str]] = {
    # ---- customers
    "Please scan the QR code on your table.": ("សូមស្កេនកូដ QR នៅលើតុរបស់អ្នក។", "请扫描餐桌上的二维码。"),
    "This QR code is not valid. Please ask our staff for help.": ("កូដ QR នេះមិនត្រឹមត្រូវទេ។ សូមសួរបុគ្គលិករបស់យើង។", "此二维码无效，请联系店员。"),
    "Your table session has ended. Please scan the QR code again.": ("វគ្គតុរបស់អ្នកបានបញ្ចប់។ សូមស្កេនកូដ QR ម្តងទៀត។", "您的餐桌会话已结束，请重新扫码。"),
    "Your table session has expired. Please scan the QR code again.": ("វគ្គតុរបស់អ្នកបានផុតកំណត់។ សូមស្កេនកូដ QR ម្តងទៀត។", "您的餐桌会话已过期，请重新扫码。"),
    "This item is no longer on the menu.": ("មុខម្ហូបនេះលែងមាននៅក្នុងម៉ឺនុយទៀតហើយ។", "此商品已不在菜单上。"),
    "An option does not belong to this item.": ("ជម្រើសមួយមិនមែនសម្រាប់មុខម្ហូបនេះទេ។", "有一个选项不属于此商品。"),
    "The same option was chosen twice.": ("ជម្រើសដូចគ្នាត្រូវបានជ្រើសពីរដង។", "同一选项被选择了两次。"),
    "Order not found.": ("រកមិនឃើញការកុម្ម៉ង់ទេ។", "找不到订单。"),
    "This order is no longer waiting for payment.": ("ការកុម្ម៉ង់នេះលែងរង់ចាំការបង់ប្រាក់ទៀតហើយ។", "此订单已不再等待付款。"),
    "The payment time for this order has ended. Please order again.": ("ពេលវេលាបង់ប្រាក់បានផុតហើយ។ សូមកុម្ម៉ង់ម្តងទៀត។", "付款时间已结束，请重新下单。"),
    "KHQR payment is not available right now. Please pay at the counter.": ("ការបង់ប្រាក់ KHQR មិនអាចប្រើបានពេលនេះទេ។ សូមបង់នៅបញ្ជរ។", "暂时无法使用 KHQR 付款，请到柜台付款。"),
    "This currency is not accepted.": ("រូបិយប័ណ្ណនេះមិនត្រូវបានទទួលទេ។", "不接受此币种。"),
    "Unknown payment method.": ("វិធីបង់ប្រាក់មិនស្គាល់។", "未知的付款方式。"),
    "Please try again.": ("សូមព្យាយាមម្តងទៀត។", "请重试。"),
    "Too many requests. Please wait and try again.": ("សំណើច្រើនពេក។ សូមរង់ចាំ ហើយព្យាយាមម្តងទៀត។", "请求过多，请稍后再试。"),
    "Not found": ("រកមិនឃើញ", "未找到"),
    # ---- sign-in and staff
    "Email or password is incorrect.": ("អ៊ីមែល ឬពាក្យសម្ងាត់មិនត្រឹមត្រូវ។", "邮箱或密码不正确。"),
    "This account has been deactivated.": ("គណនីនេះត្រូវបានបិទ។", "此账号已停用。"),
    "Please sign in again.": ("សូមចូលម្តងទៀត។", "请重新登录。"),
    "You do not have permission to do this.": ("អ្នកមិនមានសិទ្ធិធ្វើការនេះទេ។", "您无权执行此操作。"),
    "Current password is incorrect.": ("ពាក្យសម្ងាត់បច្ចុប្បន្នមិនត្រឹមត្រូវ។", "当前密码不正确。"),
    "An account with this email already exists.": ("មានគណនីប្រើអ៊ីមែលនេះរួចហើយ។", "该邮箱已有账号。"),
    "Staff member not found.": ("រកមិនឃើញបុគ្គលិក។", "找不到该员工。"),
    "Only the owner can create or promote owners.": ("មានតែម្ចាស់ទេដែលអាចបង្កើត ឬតំឡើងម្ចាស់។", "只有店主可以创建或提升为店主。"),
    "Only the owner can edit an owner account.": ("មានតែម្ចាស់ទេដែលអាចកែគណនីម្ចាស់។", "只有店主可以编辑店主账号。"),
    "Only the owner can reset an owner's password.": ("មានតែម្ចាស់ទេដែលអាចកំណត់ពាក្យសម្ងាត់ម្ចាស់ឡើងវិញ។", "只有店主可以重置店主密码。"),
    "You cannot give permissions you do not have.": ("អ្នកមិនអាចផ្តល់សិទ្ធិដែលអ្នកមិនមានទេ។", "您不能授予自己没有的权限。"),
    "You cannot deactivate or change the role of your own account.": ("អ្នកមិនអាចបិទ ឬប្តូរតួនាទីគណនីខ្លួនឯងបានទេ។", "您不能停用或更改自己账号的角色。"),
    "LAGOM must always have at least one active owner.": ("LAGOM ត្រូវតែមានម្ចាស់សកម្មយ៉ាងហោចណាស់ម្នាក់។", "LAGOM 必须至少有一位在职店主。"),
    "Password must be at least 10 characters": ("ពាក្យសម្ងាត់ត្រូវមានយ៉ាងហោចណាស់ ១០ តួអក្សរ", "密码至少需要 10 个字符"),
    "Use both upper- and lower-case letters": ("ប្រើអក្សរធំ និងអក្សរតូច", "请同时使用大写和小写字母"),
    "Include at least one number": ("ដាក់លេខយ៉ាងហោចណាស់មួយ", "至少包含一个数字"),
    # ---- POS, payments, kitchen
    "Choose an active table.": ("សូមជ្រើសរើសតុដែលកំពុងប្រើ។", "请选择可用的餐桌。"),
    "You are not allowed to give discounts.": ("អ្នកមិនមានសិទ្ធិបញ្ចុះតម្លៃទេ។", "您无权给予折扣。"),
    "Please give a reason for the discount.": ("សូមផ្តល់មូលហេតុនៃការបញ្ចុះតម្លៃ។", "请填写折扣原因。"),
    "The discount is larger than the order.": ("ការបញ្ចុះតម្លៃធំជាងការកុម្ម៉ង់។", "折扣金额大于订单金额。"),
    "This order is not waiting for payment.": ("ការកុម្ម៉ង់នេះមិនកំពុងរង់ចាំការបង់ប្រាក់ទេ។", "此订单不在待付款状态。"),
    "The cash received is less than the amount due.": ("សាច់ប្រាក់ទទួលបានតិចជាងចំនួនត្រូវបង់។", "实收金额少于应付金额。"),
    "This order was already paid.": ("ការកុម្ម៉ង់នេះបានបង់រួចហើយ។", "此订单已付款。"),
    "That order is not waiting for a KHQR payment.": ("ការកុម្ម៉ង់នោះមិនកំពុងរង់ចាំការបង់ KHQR ទេ។", "该订单不在等待 KHQR 付款。"),
    "This bank payment is already linked to an order.": ("ការបង់ប្រាក់នេះបានភ្ជាប់ទៅការកុម្ម៉ង់រួចហើយ។", "此银行付款已关联订单。"),
    "The amount does not match this order.": ("ចំនួនទឹកប្រាក់មិនត្រូវនឹងការកុម្ម៉ង់នេះទេ។", "金额与此订单不符。"),
    "This order is already closed.": ("ការកុម្ម៉ង់នេះបានបិទរួចហើយ។", "此订单已关闭。"),
    "This order is paid. Only a manager who can refund may cancel it.": ("ការកុម្ម៉ង់នេះបានបង់ហើយ។ មានតែអ្នកគ្រប់គ្រងដែលអាចសងប្រាក់ទេដែលអាចលុបចោលបាន។", "此订单已付款，只有可退款的经理才能取消。"),
    "This refund is already recorded.": ("ការសងប្រាក់នេះបានកត់ត្រារួចហើយ។", "此退款已记录。"),
    "This order is not in the kitchen queue.": ("ការកុម្ម៉ង់នេះមិននៅក្នុងជួរផ្ទះបាយទេ។", "此订单不在厨房队列中。"),
    "This order has nothing for this station.": ("ការកុម្ម៉ង់នេះគ្មានមុខម្ហូបសម្រាប់ផ្នែកនេះទេ។", "此订单没有该工作站的商品。"),
    "Mark the items ready before serving.": ("សូមសម្គាល់ថារួចរាល់មុនពេលបម្រើ។", "请先标记完成再上餐。"),
    "Mark the item ready before serving.": ("សូមសម្គាល់ថារួចរាល់មុនពេលបម្រើ។", "请先标记完成再上餐。"),
    "You do not have access to this station.": ("អ្នកមិនអាចចូលផ្នែកនេះបានទេ។", "您无权访问此工作站。"),
    # ---- admin
    "A table with this name already exists.": ("មានតុឈ្មោះនេះរួចហើយ។", "已有同名餐桌。"),
    "A category with this short name already exists.": ("មានប្រភេទឈ្មោះខ្លីនេះរួចហើយ។", "已有相同简称的分类。"),
    "An ingredient with this name already exists.": ("មានគ្រឿងផ្សំឈ្មោះនេះរួចហើយ។", "已有同名食材。"),
    "Choose a category.": ("សូមជ្រើសរើសប្រភេទ។", "请选择分类。"),
    "Exchange rate looks wrong (1000–10000).": ("អត្រាប្តូរប្រាក់មើលទៅមិនត្រឹមត្រូវ (1000–10000)។", "汇率看起来不正确（1000–10000）。"),
    "Nothing to change.": ("គ្មានអ្វីត្រូវផ្លាស់ប្តូរទេ។", "没有需要更改的内容。"),
    "The same ingredient is listed twice.": ("គ្រឿងផ្សំដូចគ្នាត្រូវបានរាយពីរដង។", "同一食材被列了两次。"),
    "That option does not belong to this product.": ("ជម្រើសនោះមិនមែនសម្រាប់មុខម្ហូបនេះទេ។", "该选项不属于此商品。"),
    "Choose a period of one year or less.": ("សូមជ្រើសរយៈពេលមួយឆ្នាំ ឬតិចជាងនេះ។", "请选择一年或更短的期间。"),
    "No active tables to print.": ("គ្មានតុដែលកំពុងប្រើសម្រាប់បោះពុម្ពទេ។", "没有可打印的餐桌。"),
}

# Messages that contain a product/option/group name: translated without the name
PATTERNS: list[tuple[re.Pattern, tuple[str, str]]] = [
    (re.compile(r"^.+ is sold out right now\.$"), ("មុខម្ហូបនេះអស់ហើយពេលនេះ។", "此商品暂时售罄。")),
    (re.compile(r"^.+ is not available right now\.$"), ("ជម្រើសនេះមិនមានពេលនេះទេ។", "此选项暂不可选。")),
    (re.compile(r"^Please choose .+\.$"), ("សូមជ្រើសរើសជម្រើសដែលចាំបាច់។", "请选择必选项。")),
    (re.compile(r"^Too many choices for .+\.$"), ("ជម្រើសច្រើនពេក។", "选择的选项过多。")),
]


def pick_language(accept_language: str | None) -> str:
    """'km-KH,km;q=0.9,en;q=0.8' -> 'km'. Only en, km and zh are supported."""
    for part in (accept_language or "").split(","):
        code = part.split(";")[0].strip().lower()[:2]
        if code in LANGS:
            return code
    return "en"


def translate(message: str, lang: str) -> str:
    if lang == "en" or not isinstance(message, str):
        return message
    idx = 0 if lang == "km" else 1
    if message in MESSAGES:
        return MESSAGES[message][idx]
    # "Password must… Use both…" may come joined with a space: translate each sentence part
    parts = [p for p in MESSAGES if p in message and len(p) > 20]
    if parts and message.startswith(parts[0][:10]):
        out = message
        for p in parts:
            out = out.replace(p, MESSAGES[p][idx])
        return out
    for pattern, tr in PATTERNS:
        if pattern.match(message):
            return tr[idx]
    return message
