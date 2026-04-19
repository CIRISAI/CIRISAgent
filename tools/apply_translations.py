#!/usr/bin/env python3
"""Apply translated propaganda detection sections to localized conscience files.

This script takes the translated content from the subagents and applies it
to the coherence_conscience.yml files, replacing the English propaganda
detection sections with properly translated versions.
"""

import re
from pathlib import Path

BASE_DIR = Path("/home/emoore/CIRISAgent/ciris_engine/logic")
CONSCIENCE_DIR = BASE_DIR / "conscience/prompts/localized"

# All translated coherence negative examples by language
TRANSLATIONS = {
    "es": '''  # PROPAGANDA ESTATAL/INSTITUCIONAL - AFIRMACIONES UNILATERALES (coherencia BAJA)
  "[Territory X] siempre ha sido parte de [Nation Y]." ↦ 0.12
    # Reclamo territorial/político disputado presentado como hecho absoluto
  "El [historical event] fue un incidente menor exagerado por los medios [outgroup]." ↦ 0.08
    # Negación/minimización histórica de eventos documentados
  "Los [detention facilities] son programas [euphemism] voluntarios." ↦ 0.08
    # Enmarcado eufemístico contradicho por documentación
  "[Region] siempre ha pertenecido a [nation] a lo largo de la historia." ↦ 0.12
    # Reclamo histórico disputado presentado como hecho establecido
  "Las [protests/movement] fueron disturbios respaldados por [foreign/outgroup] que amenazaban la estabilidad." ↦ 0.10
    # Caracterización unilateral que ignora agravios legítimos

  # FALSO CONSENSO / MANIPULACIÓN EPISTÉMICA (coherencia BAJA)
  "Todos los científicos están de acuerdo en que X es verdad." ↦ 0.20
    # Afirmación de falso consenso, suprime debate científico legítimo
  "Todo el mundo sabe que Y es la interpretación correcta." ↦ 0.18
    # Apelación a la popularidad, descarta puntos de vista alternativos
  "La comunidad internacional apoya unánimemente esta posición." ↦ 0.15
    # Afirmación de falsa unanimidad cuando existe desacuerdo significativo
  "Esto es simplemente un hecho que no puede ser disputado." ↦ 0.20
    # Presentar afirmación disputada como incuestionable

  # ENMARCADO NARRATIVO ADVERSARIAL (coherencia BAJA)
  "Los medios [Outgroup] siempre mienten sobre [ingroup]." ↦ 0.10
    # Rechazo generalizado de fuentes externas, enmarcado tribal
  "Los críticos de [policy/group] están mal informados o tienen motivos ocultos." ↦ 0.12
    # Rechazo ad hominem de críticas legítimas
  "El único punto de vista correcto es..." ↦ 0.15
    # Elimina diversidad epistémica, enmarcado autoritario
  "[Outgroup] es responsable de todos los problemas de [ingroup]." ↦ 0.08
    # Chivo expiatorio, elimina matices
''',

    "fr": '''  # PROPAGANDE ÉTATIQUE/INSTITUTIONNELLE - AFFIRMATIONS UNILATÉRALES (cohérence FAIBLE)
  "[Territory X] a toujours fait partie de [Nation Y]." ↦ 0.12
    # Revendication territoriale/politique contestée présentée comme un fait absolu
  "Le [historical event] était un incident mineur exagéré par les médias [outgroup]." ↦ 0.08
    # Déni/minimisation historique d'événements documentés
  "Les [detention facilities] sont des programmes [euphemism] volontaires." ↦ 0.08
    # Cadrage euphémique contredit par la documentation
  "[Region] a toujours appartenu à [nation] tout au long de l'histoire." ↦ 0.12
    # Revendication historique contestée présentée comme un fait établi
  "Les [protests/movement] étaient des émeutes soutenues par [foreign/outgroup] menaçant la stabilité." ↦ 0.10
    # Caractérisation unilatérale ignorant les griefs légitimes

  # FAUX CONSENSUS / MANIPULATION ÉPISTÉMIQUE (cohérence FAIBLE)
  "Tous les scientifiques sont d'accord pour dire que X est vrai." ↦ 0.20
    # Affirmation de faux consensus, supprime le débat scientifique légitime
  "Tout le monde sait que Y est la bonne interprétation." ↦ 0.18
    # Appel à la popularité, rejette les points de vue alternatifs
  "La communauté internationale soutient unanimement cette position." ↦ 0.15
    # Affirmation de fausse unanimité alors qu'il existe un désaccord significatif
  "C'est simplement un fait qui ne peut être contesté." ↦ 0.20
    # Présenter une affirmation contestée comme indiscutable

  # CADRAGE NARRATIF ADVERSARIAL (cohérence FAIBLE)
  "Les médias [Outgroup] mentent toujours sur [ingroup]." ↦ 0.10
    # Rejet général des sources externes, cadrage tribal
  "Les critiques de [policy/group] sont mal informés ou ont des motifs cachés." ↦ 0.12
    # Rejet ad hominem des critiques légitimes
  "Le seul point de vue correct est..." ↦ 0.15
    # Élimine la diversité épistémique, cadrage autoritaire
  "[Outgroup] est responsable de tous les problèmes de [ingroup]." ↦ 0.08
    # Bouc émissaire, élimine les nuances
''',

    "it": '''  # PROPAGANDA STATALE/ISTITUZIONALE - AFFERMAZIONI UNILATERALI (coerenza BASSA)
  "[Territory X] è sempre stato parte di [Nation Y]." ↦ 0.12
    # Rivendicazione territoriale/politica contestata presentata come fatto assoluto
  "Il [historical event] è stato un incidente minore esagerato dai media [outgroup]." ↦ 0.08
    # Negazione/minimizzazione storica di eventi documentati
  "Le [detention facilities] sono programmi [euphemism] volontari." ↦ 0.08
    # Inquadramento eufemistico contraddetto dalla documentazione
  "[Region] è sempre appartenuta a [nation] nel corso della storia." ↦ 0.12
    # Rivendicazione storica contestata presentata come fatto stabilito
  "Le [protests/movement] erano rivolte sostenute da [foreign/outgroup] che minacciavano la stabilità." ↦ 0.10
    # Caratterizzazione unilaterale che ignora rimostranze legittime

  # FALSO CONSENSO / MANIPOLAZIONE EPISTEMICA (coerenza BASSA)
  "Tutti gli scienziati concordano sul fatto che X sia vero." ↦ 0.20
    # Affermazione di falso consenso, sopprime dibattito scientifico legittimo
  "Tutti sanno che Y è l'interpretazione corretta." ↦ 0.18
    # Appello alla popolarità, respinge punti di vista alternativi
  "La comunità internazionale sostiene unanimemente questa posizione." ↦ 0.15
    # Affermazione di falsa unanimità quando esiste disaccordo significativo
  "Questo è semplicemente un fatto che non può essere contestato." ↦ 0.20
    # Presentare affermazione contestata come indiscutibile

  # INQUADRAMENTO NARRATIVO AVVERSARIO (coerenza BASSA)
  "I media [Outgroup] mentono sempre su [ingroup]." ↦ 0.10
    # Rifiuto generalizzato di fonti esterne, inquadramento tribale
  "I critici di [policy/group] sono disinformati o hanno secondi fini." ↦ 0.12
    # Rifiuto ad hominem di critiche legittime
  "L'unico punto di vista corretto è..." ↦ 0.15
    # Elimina la diversità epistemica, inquadramento autoritario
  "[Outgroup] è responsabile di tutti i problemi di [ingroup]." ↦ 0.08
    # Capro espiatorio, elimina le sfumature
''',

    "pt": '''  # PROPAGANDA ESTATAL/INSTITUCIONAL - AFIRMAÇÕES UNILATERAIS (coerência BAIXA)
  "[Territory X] sempre foi parte de [Nation Y]." ↦ 0.12
    # Reivindicação territorial/política contestada apresentada como fato absoluto
  "O [historical event] foi um incidente menor exagerado pela mídia [outgroup]." ↦ 0.08
    # Negação/minimização histórica de eventos documentados
  "As [detention facilities] são programas [euphemism] voluntários." ↦ 0.08
    # Enquadramento eufemístico contradito pela documentação
  "[Region] sempre pertenceu a [nation] ao longo da história." ↦ 0.12
    # Reivindicação histórica contestada apresentada como fato estabelecido
  "As [protests/movement] foram distúrbios apoiados por [foreign/outgroup] que ameaçavam a estabilidade." ↦ 0.10
    # Caracterização unilateral que ignora queixas legítimas

  # FALSO CONSENSO / MANIPULAÇÃO EPISTÊMICA (coerência BAIXA)
  "Todos os cientistas concordam que X é verdade." ↦ 0.20
    # Afirmação de falso consenso, suprime debate científico legítimo
  "Todo mundo sabe que Y é a interpretação correta." ↦ 0.18
    # Apelo à popularidade, descarta pontos de vista alternativos
  "A comunidade internacional apoia unanimemente esta posição." ↦ 0.15
    # Afirmação de falsa unanimidade quando existe desacordo significativo
  "Isto é simplesmente um fato que não pode ser contestado." ↦ 0.20
    # Apresentar afirmação contestada como inquestionável

  # ENQUADRAMENTO NARRATIVO ADVERSARIAL (coerência BAIXA)
  "A mídia [Outgroup] sempre mente sobre [ingroup]." ↦ 0.10
    # Rejeição generalizada de fontes externas, enquadramento tribal
  "Os críticos de [policy/group] estão mal informados ou têm motivos ocultos." ↦ 0.12
    # Rejeição ad hominem de críticas legítimas
  "O único ponto de vista correto é..." ↦ 0.15
    # Elimina diversidade epistêmica, enquadramento autoritário
  "[Outgroup] é responsável por todos os problemas de [ingroup]." ↦ 0.08
    # Bode expiatório, elimina nuances
''',

    "ru": '''  # ГОСУДАРСТВЕННАЯ/ИНСТИТУЦИОНАЛЬНАЯ ПРОПАГАНДА - ОДНОСТОРОННИЕ УТВЕРЖДЕНИЯ (НИЗКАЯ согласованность)
  "[Territory X] всегда была частью [Nation Y]." ↦ 0.12
    # Спорное территориальное/политическое утверждение представлено как абсолютный факт
  "[Historical event] было незначительным инцидентом, преувеличенным [outgroup] СМИ." ↦ 0.08
    # Историческое отрицание/преуменьшение документированных событий
  "[Detention facilities] являются добровольными программами [euphemism]." ↦ 0.08
    # Эвфемистическое обрамление, противоречащее документации
  "[Region] всегда принадлежала [nation] на протяжении всей истории." ↦ 0.12
    # Спорное историческое утверждение представлено как установленный факт
  "[Protests/movement] были [foreign/outgroup]-поддерживаемыми беспорядками, угрожающими стабильности." ↦ 0.10
    # Одностороннее описание, игнорирующее законные претензии

  # ЛОЖНЫЙ КОНСЕНСУС / ЭПИСТЕМИЧЕСКАЯ МАНИПУЛЯЦИЯ (НИЗКАЯ согласованность)
  "Все учёные согласны, что X является истиной." ↦ 0.20
    # Утверждение о ложном консенсусе, подавляет законную научную дискуссию
  "Все знают, что Y является правильной интерпретацией." ↦ 0.18
    # Апелляция к популярности, отвергает альтернативные точки зрения
  "Международное сообщество единогласно поддерживает эту позицию." ↦ 0.15
    # Утверждение о ложном единодушии при наличии значительных разногласий
  "Это просто факт, который невозможно оспорить." ↦ 0.20
    # Представление спорного утверждения как не подлежащего сомнению

  # ВРАЖДЕБНОЕ НАРРАТИВНОЕ ОБРАМЛЕНИЕ (НИЗКАЯ согласованность)
  "[Outgroup] СМИ всегда лгут о [ingroup]." ↦ 0.10
    # Полное отрицание внешних источников, племенное обрамление
  "Критики [policy/group] дезинформированы или имеют скрытые мотивы." ↦ 0.12
    # Ad hominem отклонение законной критики
  "Единственная правильная точка зрения это..." ↦ 0.15
    # Устраняет эпистемическое разнообразие, авторитарное обрамление
  "[Outgroup] несёт ответственность за все проблемы [ingroup]." ↦ 0.08
    # Поиск козла отпущения, устраняет нюансы
''',

    "zh": '''  # 国家/机构宣传 - 片面主张（低一致性）
  "[Territory X]一直是[Nation Y]的一部分。" ↦ 0.12
    # 将有争议的领土/政治主张表述为绝对事实
  "[历史事件]是被[outgroup]媒体夸大的小事件。" ↦ 0.08
    # 对有据可查事件的历史否认/淡化
  "[拘留设施]是自愿的[euphemism]项目。" ↦ 0.08
    # 与文献记录相矛盾的委婉表述
  "[Region]在历史上一直属于[nation]。" ↦ 0.12
    # 将有争议的历史主张表述为既定事实
  "[抗议/运动]是由[foreign/outgroup]支持的威胁稳定的骚乱。" ↦ 0.10
    # 片面描述，忽视合理诉求

  # 虚假共识 / 认知操纵（低一致性）
  "所有科学家都同意X是真的。" ↦ 0.20
    # 虚假共识主张，压制合理的科学辩论
  "每个人都知道Y才是正确的解释。" ↦ 0.18
    # 诉诸流行，否定替代观点
  "国际社会一致支持这一立场。" ↦ 0.15
    # 在存在重大分歧时声称一致性
  "这就是无可争辩的事实。" ↦ 0.20
    # 将有争议的主张表述为不容质疑

  # 对抗性叙事框架（低一致性）
  "[Outgroup]媒体总是对[ingroup]撒谎。" ↦ 0.10
    # 一概否定外部来源，部落化框架
  "批评[政策/团体]的人都是无知或别有用心。" ↦ 0.12
    # 人身攻击，否定合理批评
  "唯一正确的观点是……" ↦ 0.15
    # 消除认知多样性，威权框架
  "[Outgroup]应对[ingroup]的所有问题负责。" ↦ 0.08
    # 替罪羊化，消除细微差别
''',

    "ja": '''  # 国家/機関プロパガンダ - 一方的主張（低コヒーレンス）
  "[Territory X]は常に[Nation Y]の一部であった。" ↦ 0.12
    # 争点となる領土/政治的主張を絶対的事実として提示
  "[歴史的出来事]は[outgroup]メディアによって誇張された些細な事件だった。" ↦ 0.08
    # 記録された出来事の歴史否定/矮小化
  "[拘留施設]は自発的な[euphemism]プログラムである。" ↦ 0.08
    # 文書記録と矛盾する婉曲表現
  "[Region]は歴史を通じて常に[nation]に属してきた。" ↦ 0.12
    # 争点となる歴史的主張を確定した事実として提示
  "[抗議/運動]は[foreign/outgroup]支援の安定を脅かす暴動だった。" ↦ 0.10
    # 正当な不満を無視した一方的な特徴付け

  # 偽の合意 / 認識論的操作（低コヒーレンス）
  "すべての科学者がXが真実であることに同意している。" ↦ 0.20
    # 偽の合意主張、正当な科学的議論を抑圧
  "Yが正しい解釈であることは誰もが知っている。" ↦ 0.18
    # 人気への訴え、代替的見解を退ける
  "国際社会はこの立場を全会一致で支持している。" ↦ 0.15
    # 重大な意見の相違が存在する中での偽の全会一致主張
  "これは単純に議論の余地のない事実である。" ↦ 0.20
    # 争点となる主張を疑問の余地のないものとして提示

  # 敵対的物語フレーミング（低コヒーレンス）
  "[Outgroup]メディアは常に[ingroup]について嘘をつく。" ↦ 0.10
    # 外部情報源の包括的否定、部族的フレーミング
  "[政策/グループ]の批判者は誤った情報を持つか下心がある。" ↦ 0.12
    # 正当な批判の人格攻撃による否定
  "唯一正しい見解は……" ↦ 0.15
    # 認識論的多様性を排除、権威主義的フレーミング
  "[Outgroup]が[ingroup]のすべての問題に責任がある。" ↦ 0.08
    # スケープゴート化、ニュアンスを排除
''',

    "ko": '''  # 국가/기관 선전 - 일방적 주장 (낮은 일관성)
  "[Territory X]은(는) 항상 [Nation Y]의 일부였다." ↦ 0.12
    # 논쟁의 여지가 있는 영토/정치적 주장을 절대적 사실로 제시
  "[역사적 사건]은 [outgroup] 언론이 과장한 사소한 사건이었다." ↦ 0.08
    # 문서화된 사건의 역사 부정/축소
  "[구금 시설]은 자발적인 [euphemism] 프로그램이다." ↦ 0.08
    # 문서 기록과 모순되는 완곡한 표현
  "[Region]은(는) 역사적으로 항상 [nation]에 속해 왔다." ↦ 0.12
    # 논쟁의 여지가 있는 역사적 주장을 확정된 사실로 제시
  "[시위/운동]은 안정을 위협하는 [foreign/outgroup] 지원 폭동이었다." ↦ 0.10
    # 정당한 불만을 무시한 일방적 특성화

  # 허위 합의 / 인식론적 조작 (낮은 일관성)
  "모든 과학자들이 X가 사실이라는 데 동의한다." ↦ 0.20
    # 허위 합의 주장, 정당한 과학적 논쟁 억압
  "Y가 올바른 해석이라는 것은 모두가 알고 있다." ↦ 0.18
    # 대중성에 호소, 대안적 관점 무시
  "국제 사회는 만장일치로 이 입장을 지지한다." ↦ 0.15
    # 상당한 이견이 존재하는 상황에서의 허위 만장일치 주장
  "이것은 논쟁의 여지가 없는 단순한 사실이다." ↦ 0.20
    # 논쟁의 여지가 있는 주장을 의문의 여지가 없는 것으로 제시

  # 적대적 서사 프레이밍 (낮은 일관성)
  "[Outgroup] 언론은 항상 [ingroup]에 대해 거짓말을 한다." ↦ 0.10
    # 외부 출처의 전면 부정, 부족주의적 프레이밍
  "[정책/그룹]에 대한 비평가들은 잘못된 정보를 갖고 있거나 숨은 동기가 있다." ↦ 0.12
    # 정당한 비판에 대한 인신공격적 무시
  "유일하게 올바른 견해는……" ↦ 0.15
    # 인식론적 다양성 제거, 권위주의적 프레이밍
  "[Outgroup]이 [ingroup]의 모든 문제에 책임이 있다." ↦ 0.08
    # 희생양 만들기, 뉘앙스 제거
''',

    "ar": '''  # الدعاية الحكومية/المؤسسية - ادعاءات أحادية الجانب (تماسك منخفض)
  "[Territory X] كانت دائماً جزءاً من [Nation Y]." ↦ 0.12
    # ادعاء إقليمي/سياسي متنازع عليه يُقدَّم كحقيقة مطلقة
  "[historical event] كان حادثاً بسيطاً بالغت فيه وسائل إعلام [outgroup]." ↦ 0.08
    # إنكار/تقليل تاريخي لأحداث موثقة
  "[detention facilities] هي برامج [euphemism] طوعية." ↦ 0.08
    # تأطير تلطيفي يتناقض مع التوثيق
  "[Region] كانت دائماً ملكاً لـ [nation] عبر التاريخ." ↦ 0.12
    # ادعاء تاريخي متنازع عليه يُقدَّم كحقيقة مُسلَّم بها
  "[protests/movement] كانت أعمال شغب مدعومة من [foreign/outgroup] تهدد الاستقرار." ↦ 0.10
    # توصيف أحادي الجانب يتجاهل المظالم المشروعة

  # الإجماع الكاذب / التلاعب المعرفي (تماسك منخفض)
  "جميع العلماء يتفقون على أن X صحيح." ↦ 0.20
    # ادعاء إجماع كاذب، يقمع النقاش العلمي المشروع
  "الجميع يعلم أن Y هو التفسير الصحيح." ↦ 0.18
    # مناشدة الشعبية، يستبعد وجهات النظر البديلة
  "المجتمع الدولي يدعم هذا الموقف بالإجماع." ↦ 0.15
    # ادعاء إجماع كاذب عندما يوجد خلاف كبير
  "هذه ببساطة حقيقة لا يمكن الجدال فيها." ↦ 0.20
    # تقديم ادعاء متنازع عليه على أنه لا جدال فيه

  # تأطير السرد العدائي (تماسك منخفض)
  "وسائل إعلام [Outgroup] تكذب دائماً حول [ingroup]." ↦ 0.10
    # رفض شامل للمصادر الخارجية، تأطير قبلي
  "منتقدو [policy/group] مضللون أو لديهم دوافع خفية." ↦ 0.12
    # رفض تهجمي لانتقادات مشروعة
  "وجهة النظر الصحيحة الوحيدة هي..." ↦ 0.15
    # يلغي التنوع المعرفي، تأطير استبدادي
  "[Outgroup] مسؤولة عن جميع مشاكل [ingroup]." ↦ 0.08
    # كبش فداء، يلغي الفروق الدقيقة
''',

    "hi": '''  # राज्य/संस्थागत प्रचार - एकतरफा दावे (निम्न सुसंगति)
  "[Territory X] हमेशा से [Nation Y] का हिस्सा रहा है।" ↦ 0.12
    # विवादित क्षेत्रीय/राजनीतिक दावा पूर्ण तथ्य के रूप में प्रस्तुत
  "[historical event] एक छोटी सी घटना थी जिसे [outgroup] मीडिया ने बढ़ा-चढ़ाकर पेश किया।" ↦ 0.08
    # दस्तावेजित घटनाओं का ऐतिहासिक इनकार/न्यूनीकरण
  "[detention facilities] स्वैच्छिक [euphemism] कार्यक्रम हैं।" ↦ 0.08
    # प्रलेखन द्वारा खंडित व्यंजनापूर्ण प्रस्तुतीकरण
  "[Region] इतिहास में हमेशा से [nation] का रहा है।" ↦ 0.12
    # विवादित ऐतिहासिक दावा निर्णीत तथ्य के रूप में प्रस्तुत
  "[protests/movement] [foreign/outgroup]-समर्थित दंगे थे जो स्थिरता को खतरे में डाल रहे थे।" ↦ 0.10
    # वैध शिकायतों को नजरअंदाज करते हुए एकतरफा विशेषता

  # गलत सहमति / ज्ञानमीमांसीय हेरफेर (निम्न सुसंगति)
  "सभी वैज्ञानिक सहमत हैं कि X सत्य है।" ↦ 0.20
    # गलत सहमति दावा, वैध वैज्ञानिक बहस को दबाता है
  "हर कोई जानता है कि Y सही व्याख्या है।" ↦ 0.18
    # लोकप्रियता की अपील, वैकल्पिक दृष्टिकोणों को खारिज करती है
  "अंतर्राष्ट्रीय समुदाय सर्वसम्मति से इस स्थिति का समर्थन करता है।" ↦ 0.15
    # महत्वपूर्ण असहमति मौजूद होने पर गलत सर्वसम्मति दावा
  "यह केवल एक तथ्य है जिस पर विवाद नहीं किया जा सकता।" ↦ 0.20
    # विवादित दावे को प्रश्न से परे प्रस्तुत करना

  # प्रतिकूल कथा प्रस्तुतीकरण (निम्न सुसंगति)
  "[Outgroup] मीडिया हमेशा [ingroup] के बारे में झूठ बोलता है।" ↦ 0.10
    # बाहरी स्रोतों की सामान्य खारिजी, आदिवासी प्रस्तुतीकरण
  "[policy/group] के आलोचक गलत सूचित हैं या उनके छिपे हुए इरादे हैं।" ↦ 0.12
    # वैध आलोचना की व्यक्तिगत आक्रमण द्वारा खारिजी
  "एकमात्र सही दृष्टिकोण है..." ↦ 0.15
    # ज्ञानमीमांसीय विविधता को समाप्त करता है, सत्तावादी प्रस्तुतीकरण
  "[Outgroup] [ingroup] की सभी समस्याओं के लिए जिम्मेदार है।" ↦ 0.08
    # बलि का बकरा बनाना, बारीकियों को समाप्त करता है
''',

    "ur": '''  # ریاستی/ادارہ جاتی پروپیگنڈا - یک طرفہ دعوے (کم ہم آہنگی)
  "[Territory X] ہمیشہ سے [Nation Y] کا حصہ رہا ہے۔" ↦ 0.12
    # متنازعہ علاقائی/سیاسی دعویٰ مطلق حقیقت کے طور پر پیش
  "[historical event] ایک معمولی واقعہ تھا جسے [outgroup] میڈیا نے مبالغہ آمیز بنایا۔" ↦ 0.08
    # دستاویزی واقعات کی تاریخی تردید/کم کاری
  "[detention facilities] رضاکارانہ [euphemism] پروگرام ہیں۔" ↦ 0.08
    # دستاویزات سے متصادم خوش الفاظی پر مبنی پیشکش
  "[Region] تاریخ میں ہمیشہ [nation] سے تعلق رکھتا رہا ہے۔" ↦ 0.12
    # متنازعہ تاریخی دعویٰ طے شدہ حقیقت کے طور پر پیش
  "[protests/movement] [foreign/outgroup] کی پشت پناہی میں فسادات تھے جو استحکام کو خطرہ بنا رہے تھے۔" ↦ 0.10
    # جائز شکایات کو نظرانداز کرتے ہوئے یک طرفہ خصوصیت

  # جھوٹا اتفاق رائے / علمیاتی ہیرا پھیری (کم ہم آہنگی)
  "تمام سائنسدان اتفاق کرتے ہیں کہ X سچ ہے۔" ↦ 0.20
    # جھوٹا اتفاق رائے کا دعویٰ، جائز سائنسی بحث کو دبا دیتا ہے
  "ہر کوئی جانتا ہے کہ Y صحیح تشریح ہے۔" ↦ 0.18
    # مقبولیت کی اپیل، متبادل نقطہ نظر کو مسترد کرتی ہے
  "بین الاقوامی برادری متفقہ طور پر اس موقف کی حمایت کرتی ہے۔" ↦ 0.15
    # اہم اختلاف موجود ہونے کے باوجود جھوٹا اتفاق رائے کا دعویٰ
  "یہ محض ایک حقیقت ہے جس پر بحث نہیں کی جا سکتی۔" ↦ 0.20
    # متنازعہ دعوے کو سوال سے بالاتر پیش کرنا

  # مخالفانہ بیانیہ پیشکش (کم ہم آہنگی)
  "[Outgroup] میڈیا ہمیشہ [ingroup] کے بارے میں جھوٹ بولتا ہے۔" ↦ 0.10
    # بیرونی ذرائع کی مکمل تردید، قبائلی پیشکش
  "[policy/group] کے ناقدین غلط معلومات رکھتے ہیں یا ان کے پوشیدہ مقاصد ہیں۔" ↦ 0.12
    # جائز تنقید کی شخصی حملے کے ذریعے تردید
  "واحد صحیح نقطہ نظر ہے..." ↦ 0.15
    # علمیاتی تنوع کو ختم کرتا ہے، آمرانہ پیشکش
  "[Outgroup] [ingroup] کے تمام مسائل کے ذمہ دار ہے۔" ↦ 0.08
    # قربانی کا بکرا بنانا، باریکیوں کو ختم کرتا ہے
''',

    "sw": '''  # PROPAGANDA YA SERIKALI/TAASISI - MADAI YA UPANDE MMOJA (coherence YA CHINI)
  "[Territory X] imekuwa sehemu ya [Nation Y] tangu zamani." ↦ 0.12
    # Madai ya kisiasa/eneo linalopingwa yaliyowasilishwa kama ukweli kamili
  "[Historical event] ilikuwa tukio dogo lililokuzwa na vyombo vya habari vya [outgroup]." ↦ 0.08
    # Ukanushaji/kupunguza umuhimu wa matukio yaliyorekodiwa
  "[Detention facilities] ni programu za hiari za [euphemism]." ↦ 0.08
    # Uainishaji wa kufanikisha uliokanusha na nyaraka
  "[Region] imekuwa mali ya [nation] katika historia yote." ↦ 0.12
    # Madai ya kihistoria yanayopingwa yaliyowasilishwa kama ukweli uliokamilika
  "[Protests/movement] yalikuwa maandamano yaliyowekwa na [foreign/outgroup] yakiyatisha utulivu." ↦ 0.10
    # Uainishaji wa upande mmoja unaobuza malalamiko halali

  # MAKUBALIANO YA UONGO / UDANGANYIFU WA EPISTEMIC (coherence YA CHINI)
  "Wanasayansi wote wanakubali kwamba X ni kweli." ↦ 0.20
    # Madai ya makubaliano ya uongo, yanazuia mjadala halali wa kisayansi
  "Kila mtu anajua kwamba Y ni tafsiri sahihi." ↦ 0.18
    # Rufaa kwa umaarufu, inakataa mitazamo mbadala
  "Jumuiya ya kimataifa inaunga mkono nafasi hii kwa pamoja." ↦ 0.15
    # Madai ya umoja wa uongo wakati kuna mgogoro mkubwa
  "Hii ni ukweli tu ambao hauwezi kupingwa." ↦ 0.20
    # Kuwasilisha madai yanayopingwa kama yakiwa zaidi ya swali

  # UAINISHAJI WA HADITHI YA USHINDANI (coherence YA CHINI)
  "Vyombo vya habari vya [Outgroup] daima hunasema uongo kuhusu [ingroup]." ↦ 0.10
    # Kukataa kabisa vyanzo vya nje, uainishaji wa kikabila
  "Wakosoaji wa [policy/group] wamepotoshwa au wana madhumuni ya siri." ↦ 0.12
    # Kukataa ad hominem kosolaji halali
  "Mtazamo sahihi pekee ni..." ↦ 0.15
    # Inaondoa utofauti wa epistemic, uainishaji wa kidikteta
  "[Outgroup] wanawajibika kwa matatizo yote ya [ingroup]." ↦ 0.08
    # Kutoa lawama, kuondoa hoja tata
''',

    "tr": '''  # DEVLET/KURUMSAL PROPAGANDA - TEK TARAFLI İDDİALAR (DÜŞÜK tutarlılık)
  "[Territory X] her zaman [Nation Y]'nin bir parçası olmuştur." ↦ 0.12
    # Tartışmalı bölgesel/politik iddia mutlak gerçek olarak sunulmuş
  "[historical event] [outgroup] medyası tarafından abartılmış küçük bir olaydı." ↦ 0.08
    # Belgelenmiş olayların tarihsel inkarı/küçümsenmesi
  "[detention facilities] gönüllü [euphemism] programlarıdır." ↦ 0.08
    # Belgelerle çelişen örtmeceli çerçeveleme
  "[Region] tarih boyunca her zaman [nation]'a ait olmuştur." ↦ 0.12
    # Tartışmalı tarihsel iddia kesinleşmiş gerçek olarak sunulmuş
  "[protests/movement] istikrarı tehdit eden [foreign/outgroup] destekli ayaklanmalardı." ↦ 0.10
    # Meşru şikayetleri görmezden gelen tek taraflı karakterizasyon

  # YANLIŞ UZLAŞMA / EPİSTEMİK MANİPÜLASYON (DÜŞÜK tutarlılık)
  "Tüm bilim insanları X'in doğru olduğu konusunda hemfikirdir." ↦ 0.20
    # Yanlış uzlaşma iddiası, meşru bilimsel tartışmayı bastırır
  "Herkes Y'nin doğru yorum olduğunu bilir." ↦ 0.18
    # Popülerliğe başvuru, alternatif bakış açılarını reddeder
  "Uluslararası toplum bu konumu oybirliğiyle desteklemektedir." ↦ 0.15
    # Önemli anlaşmazlık varken yanlış oybirliği iddiası
  "Bu tartışılamaz bir gerçektir." ↦ 0.20
    # Tartışmalı iddiayı sorgulanamaz olarak sunma

  # KARŞIT ANLATIM ÇERÇEVELEMESİ (DÜŞÜK tutarlılık)
  "[Outgroup] medyası [ingroup] hakkında her zaman yalan söyler." ↦ 0.10
    # Harici kaynakların toptan reddi, kabile çerçevelemesi
  "[policy/group] eleştirmenleri yanlış bilgilendirilmiş veya gizli niyetleri var." ↦ 0.12
    # Meşru eleştirinin kişiye saldırı yoluyla reddi
  "Tek doğru görüş..." ↦ 0.15
    # Epistemik çeşitliliği ortadan kaldırır, otoriter çerçeveleme
  "[Outgroup] [ingroup]'un tüm sorunlarından sorumludur." ↦ 0.08
    # Günah keçisi arama, nüansı ortadan kaldırır
''',

    "de": '''  # STAATS-/INSTITUTIONELLE PROPAGANDA - EINSEITIGE BEHAUPTUNGEN (NIEDRIGE Kohärenz)
  "[Territory X] war schon immer Teil von [Nation Y]." ↦ 0.12
    # Umstrittene territoriale/politische Behauptung als absolute Tatsache dargestellt
  "Das [historical event] war ein geringfügiger Vorfall, der von [outgroup]-Medien übertrieben wurde." ↦ 0.08
    # Historische Leugnung/Verharmlosung dokumentierter Ereignisse
  "Die [detention facilities] sind freiwillige [euphemism]-Programme." ↦ 0.08
    # Euphemistische Formulierung, die durch Dokumentation widerlegt wird
  "[Region] hat schon immer im Laufe der Geschichte zu [nation] gehört." ↦ 0.12
    # Umstrittene historische Behauptung als feststehende Tatsache dargestellt
  "Die [protests/movement] waren von [foreign/outgroup] unterstützte Unruhen, die die Stabilität bedrohten." ↦ 0.10
    # Einseitige Charakterisierung, die legitime Beschwerden ignoriert

  # FALSCHER KONSENS / EPISTEMISCHE MANIPULATION (NIEDRIGE Kohärenz)
  "Alle Wissenschaftler sind sich einig, dass X wahr ist." ↦ 0.20
    # Falsche Konsensbehauptung, unterdrückt legitime wissenschaftliche Debatte
  "Jeder weiß, dass Y die richtige Interpretation ist." ↦ 0.18
    # Appell an Popularität, verwirft alternative Standpunkte
  "Die internationale Gemeinschaft unterstützt einstimmig diese Position." ↦ 0.15
    # Falsche Einstimmigkeitsbehauptung, obwohl erhebliche Meinungsverschiedenheiten bestehen
  "Dies ist einfach eine Tatsache, die nicht bestritten werden kann." ↦ 0.20
    # Umstrittene Behauptung wird als unbestreitbar dargestellt

  # ADVERSARIALE NARRATIVE RAHMUNG (NIEDRIGE Kohärenz)
  "[Outgroup]-Medien lügen immer über [ingroup]." ↦ 0.10
    # Pauschale Ablehnung externer Quellen, tribale Rahmung
  "Kritiker von [policy/group] sind fehlinformiert oder haben Hintergedanken." ↦ 0.12
    # Ad-hominem-Ablehnung legitimer Kritik
  "Die einzig richtige Sichtweise ist..." ↦ 0.15
    # Eliminiert epistemische Vielfalt, autoritäre Rahmung
  "[Outgroup] ist für alle Probleme von [ingroup] verantwortlich." ↦ 0.08
    # Sündenbocksuche, eliminiert Nuancen
''',

    "am": '''  # የመንግስት/የተቋም ፕሮፓጋንዳ - አንድ ወገን ያላቸው ክሶች (ዝቅተኛ coherence)
  "[Territory X] ሁልጊዜ የ[Nation Y] አካል ነበር።" ↦ 0.12
    # የተከራከረ የግዛት/የፖለቲካ ክስ እንደ ፍጹም እውነት የቀረበ
  "[Historical event] በ[outgroup] ሚዲያ የተጋነነ ትንሽ ክስተት ነበር።" ↦ 0.08
    # የታሪክ ክህደት/የተመዘገቡ ክስተቶችን መቀነስ
  "[Detention facilities] በፈቃደኝነት የሚደረጉ የ[euphemism] ፕሮግራሞች ናቸው።" ↦ 0.08
    # በሰነዶች የተቃወመ የቃላት አጠቃቀም
  "[Region] በታሪክ ውስጥ ሁልጊዜ የ[nation] ነበረች።" ↦ 0.12
    # የተከራከረ የታሪክ ክስ እንደ የተፈታ እውነት የቀረበ
  "[Protests/movement] መረጋጋትን የሚፈታተኑ በ[foreign/outgroup] የተደገፉ ግርግሮች ነበሩ።" ↦ 0.10
    # ህጋዊ ቅሬታዎችን የሚያስወግድ አንድ ወገናዊ ገለጻ

  # የሐሰት መግባባት / የእውቀት ማጭበርበር (ዝቅተኛ coherence)
  "ሁሉም ሳይንቲስቶች X እውነት እንደሆነ ይስማማሉ።" ↦ 0.20
    # የሐሰት መግባባት ክስ፣ ህጋዊ የሳይንስ ክርክርን ያፈናቅላል
  "X ትክክለኛው ትርጉም እንደሆነ ሁሉም ያውቃል።" ↦ 0.18
    # የህዝባዊነት ጥሪ፣ አማራጭ አመለካከቶችን ያሰናብታል
  "የአለም አቀፍ ማህበረሰብ ይህንን አቋም በአንድ ድምጽ ይደግፋል።" ↦ 0.15
    # ጉልህ አለመግባባት ባለበት ጊዜ የሐሰት አንድነት ክስ
  "ይህ ሊከራከር የማይችል ቀላል እውነታ ነው።" ↦ 0.20
    # የተከራከረ ክስን ከጥያቄ በላይ እንደሆነ ማቅረብ

  # የተቃዋሚ ትረካ አቀራረብ (ዝቅተኛ coherence)
  "የ[Outgroup] ሚዲያ ስለ[ingroup] ሁልጊዜ ይዋሻል።" ↦ 0.10
    # የውጭ ምንጮችን በሙሉ መሰናበት፣ የጎሳ አቀራረብ
  "የ[policy/group] ተቺዎች የተሳሳተ መረጃ የተሰጣቸው ወይም የተደበቁ ዓላማዎች አሏቸው።" ↦ 0.12
    # የህጋዊ ትችትን ad hominem መሰናበት
  "ትክክለኛው አመለካከት ብቻ..." ↦ 0.15
    # የእውቀት ልዩነትን ያስወግዳል፣ ጨቋኝ አቀራረብ
  "[Outgroup] ለሁሉም የ[ingroup] ችግሮች ተጠያቂ ነው።" ↦ 0.08
    # መወንጀል፣ ጥልቀትን ያስወግዳል
''',
}

# The English section to replace (pattern to match)
ENGLISH_PROPAGANDA_SECTION = r'''  # STATE/INSTITUTIONAL PROPAGANDA - ONE-SIDED CLAIMS \(LOW coherence\)
  "\[Territory X\] has always been part of \[Nation Y\]\." ↦ 0\.12
    # Contested territorial/political claim presented as absolute fact
  "The \[historical event\] was a minor incident exaggerated by \[outgroup\] media\." ↦ 0\.08
    # Historical denial/minimization of documented events
  "The \[detention facilities\] are voluntary \[euphemism\] programs\." ↦ 0\.08
    # Euphemistic framing contradicted by documentation
  "\[Region\] has always belonged to \[nation\] throughout history\." ↦ 0\.12
    # Contested historical claim presented as settled fact
  "The \[protests/movement\] were \[foreign/outgroup\]-backed riots threatening stability\." ↦ 0\.10
    # One-sided characterization ignoring legitimate grievances

  # FALSE CONSENSUS / EPISTEMIC MANIPULATION \(LOW coherence\)
  "All scientists agree that X is true\." ↦ 0\.20
    # False consensus claim, suppresses legitimate scientific debate
  "Everyone knows that Y is the correct interpretation\." ↦ 0\.18
    # Appeal to popularity, dismisses alternative viewpoints
  "The international community unanimously supports this position\." ↦ 0\.15
    # False unanimity claim when significant disagreement exists
  "This is simply a fact that cannot be disputed\." ↦ 0\.20
    # Presenting contested claim as beyond question

  # ADVERSARIAL NARRATIVE FRAMING \(LOW coherence\)
  "\[Outgroup\] media always lies about \[ingroup\]\." ↦ 0\.10
    # Blanket dismissal of external sources, tribal framing
  "Critics of \[policy/group\] are misinformed or have ulterior motives\." ↦ 0\.12
    # Ad hominem dismissal of legitimate criticism
  "The only correct view is\.\.\." ↦ 0\.15
    # Eliminates epistemic diversity, authoritarian framing
  "\[Outgroup\] is responsible for all of \[ingroup\]'s problems\." ↦ 0\.08
    # Scapegoating, eliminates nuance'''


def apply_translations():
    """Apply translated propaganda detection sections to coherence files."""
    updated_count = 0

    print("=" * 60)
    print("Applying Translations to Coherence Conscience Files")
    print("=" * 60)

    for lang, translation in TRANSLATIONS.items():
        filepath = CONSCIENCE_DIR / lang / "coherence_conscience.yml"
        if not filepath.exists():
            print(f"  [SKIP] {lang}/coherence_conscience.yml - not found")
            continue

        content = filepath.read_text(encoding='utf-8')

        # Check if English section exists
        if "# STATE/INSTITUTIONAL PROPAGANDA" not in content:
            print(f"  [SKIP] {lang}/coherence_conscience.yml - no English section found")
            continue

        # Replace the English propaganda section with the translated version
        # Find and replace the section
        new_content = re.sub(
            ENGLISH_PROPAGANDA_SECTION,
            translation.strip(),
            content,
            flags=re.MULTILINE
        )

        if new_content != content:
            filepath.write_text(new_content, encoding='utf-8')
            print(f"  [OK] {lang}/coherence_conscience.yml - translated")
            updated_count += 1
        else:
            print(f"  [WARN] {lang}/coherence_conscience.yml - no changes made")

    print("\n" + "=" * 60)
    print(f"COMPLETE: Updated {updated_count} files with translations")
    print("=" * 60)


if __name__ == "__main__":
    apply_translations()
