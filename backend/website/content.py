"""Public website content model.

The site is organised around *what the visitor needs*, then the market -- not
around the Holding's subsidiaries. This module is the single source of truth
for that structure: services, markets, navigation and the copy that describes
each market/service page.

Why a Python model instead of a CMS: the content is small, changes rarely and
benefits from being reviewed in code. It also lets the same definitions drive
the HTML pages, the ``sitemap.xml``, the canonical/hreflang alternates and the
breadcrumb structured data, so those can never drift apart.

Content rules (see the project brief): never invent statistics, transaction
values, client counts, approvals, awards, partnerships, years or locations.
Where a fact is not verified it is simply absent and the copy stays
conservative.

The V2 concept is explicit that every market+service pair is its own page with
its own copy -- "do not repeat the same text and only change the country name".
``SERVICE_MARKET_CONTENT`` therefore carries, per market and per service, a
localised intro, market-specific highlights, a "what you get" list, the process
steps and a short FAQ. All of it is generic, factual and non-committal: it
describes how the service works, never a promise or a number.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# The two markets, in the order they should appear in the UI.
MARKETS: tuple[str, ...] = ("bahrain", "saudi")

# Short, URL-safe Arabic market slugs. Kept explicit rather than derived from
# the display label so a copy tweak never silently changes a public URL.
MARKET_SLUG_AR: dict[str, str] = {"bahrain": "البحرين", "saudi": "السعودية"}

MARKET_LABELS: dict[str, dict[str, str]] = {
    "bahrain": {"ar": "البحرين", "en": "Bahrain"},
    "saudi": {"ar": "المملكة العربية السعودية", "en": "Saudi Arabia"},
}

# The services that have a dedicated, indexable page per market. ``slug`` is the
# English URL segment; ``slug_ar`` is the Arabic one. Keeping both means the
# Arabic site has genuinely Arabic URLs rather than transliterations.
SERVICES: dict[str, dict] = {
    "company-formation": {
        "key": "company_formation",
        "slug": "company-formation",
        "slug_ar": "تأسيس-شركة",
        "icon": "formation",
        "title": {"ar": "تأسيس شركة", "en": "Company Formation"},
        "blurb": {
            "ar": "ابدأ إجراءات تأسيس شركتك حسب السوق المختار.",
            "en": "Start your company formation in the market you choose.",
        },
        "form": "company-formation",
    },
    "feasibility-study": {
        "key": "feasibility_study",
        "slug": "feasibility-study",
        "slug_ar": "دراسة-جدوى",
        "icon": "feasibility",
        "title": {"ar": "دراسة جدوى", "en": "Feasibility Study"},
        "blurb": {
            "ar": "اطلب دراسة للسوق البحريني أو السعودي قبل الاستثمار.",
            "en": "Commission a market study for Bahrain or Saudi Arabia.",
        },
        "form": "feasibility",
    },
    "opportunities": {
        "key": "opportunities",
        "slug": "opportunities",
        "slug_ar": "الفرص-والمشاريع",
        "icon": "opportunities",
        "title": {"ar": "مشاريع وفرص للبيع", "en": "Projects & Opportunities"},
        "blurb": {
            "ar": "استعرض فرصًا متاحة في البحرين أو السعودية.",
            "en": "Browse available opportunities in Bahrain or Saudi Arabia.",
        },
        "form": None,
    },
    "investment": {
        "key": "investment",
        "slug": "investment",
        "slug_ar": "الاستثمار",
        "icon": "investment",
        "title": {"ar": "فرص استثمار", "en": "Investment Opportunities"},
        "blurb": {
            "ar": "فرص استثمارية وشراكات في السوقين.",
            "en": "Investment and partnership opportunities in both markets.",
        },
        "form": "investment",
    },
}

# Market-level framing, shared by every service page in that market.
MARKET_CONTENT: dict[str, dict] = {
    "bahrain": {
        "meta": {
            "ar": {
                "title": "البحرين",
                "description": "خدمات الأعمال والاستثمار في مملكة البحرين عبر سفير القابضة.",
            },
            "en": {
                "title": "Bahrain",
                "description": "Business and investment services in the Kingdom of Bahrain with Safir Holding.",
            },
        },
        "intro": {
            "ar": "مملكة البحرين سوق مفتوح للأعمال، وقاعدة مناسبة للانطلاق نحو المنطقة.",
            "en": "The Kingdom of Bahrain is an open business market and a practical base for the region.",
        },
        "highlights": {
            "ar": [
                "بيئة أعمال مرنة ومنفتحة على المستثمر الأجنبي",
                "قرب جغرافي من السوق السعودي",
                "قطاعات خدماتية وتجارية وصناعية متنوعة",
            ],
            "en": [
                "A flexible business environment open to foreign investors",
                "Geographic proximity to the Saudi market",
                "A broad mix of services, trading and industrial sectors",
            ],
        },
    },
    "saudi": {
        "meta": {
            "ar": {
                "title": "المملكة العربية السعودية",
                "description": "خدمات الأعمال والاستثمار في المملكة العربية السعودية عبر سفير القابضة.",
            },
            "en": {
                "title": "Saudi Arabia",
                "description": "Business and investment services in Saudi Arabia with Safir Holding.",
            },
        },
        "intro": {
            "ar": "السوق السعودي هو الأكبر في المنطقة، ويستقطب المشاريع والمستثمرين.",
            "en": "The Saudi market is the region's largest and continues to attract projects and investors.",
        },
        "highlights": {
            "ar": [
                "سوق واسع ونمو مستمر في القطاعات غير النفطية",
                "مسارات متعددة للترخيص والاستثمار حسب النشاط",
                "مدن رئيسية ذات أولويات اقتصادية واضحة",
            ],
            "en": [
                "A large market with sustained growth in non-oil sectors",
                "Multiple licensing and investment paths by activity",
                "Major cities with clear economic priorities",
            ],
        },
    },
}


# --------------------------------------------------------------------------
# per market + service page content
# --------------------------------------------------------------------------
# Each entry is deliberately different per market: the local specifics (cities,
# entity types, timeline shape) are what make the page a genuine local page
# rather than a swapped label. No statistics, no fees, no guarantees.
SERVICE_MARKET_CONTENT: dict[str, dict[str, dict]] = {
    "company-formation": {
        "bahrain": {
            "meta": {
                "ar": {
                    "title": "تأسيس شركة في البحرين",
                    "description": "ساعد شركتك على الانطلاق في مملكة البحرين: النشاط، الشركاء، نوع المستثمر والمتطلبات المحلية، بطلب واحد.",
                },
                "en": {
                    "title": "Company Formation in Bahrain",
                    "description": "Set up your company in the Kingdom of Bahrain: activity, partners, investor type and local requirements, in one request.",
                },
            },
            "intro": {
                "ar": "نساعدك على تأسيس شركتك في مملكة البحرين بدءًا من اختيار النشاط وهيكل الشركاء وصولًا إلى استكمال المتطلبات المحلية.",
                "en": "We help you form your company in the Kingdom of Bahrain, from choosing the activity and partner structure through to completing the local requirements.",
            },
            "highlights": {
                "ar": [
                    "هياكل ملكية مرنة تناسب الشركات الصغيرة والمتوسطة",
                    "خيارات متعددة للشركاء ولنوع المستثمر: فرد أو شركة",
                    "إمكانية الحصول على عنوان أو مكتب عند الحاجة",
                ],
                "en": [
                    "Flexible ownership structures suited to small and medium companies",
                    "Multiple options for partners and investor type: individual or company",
                    "The option of an address or office when needed",
                ],
            },
            "deliverables": {
                "ar": [
                    "مراجعة النشاط المطلوب وهيكل الشركاء",
                    "توضيح المتطلبات المحلية وخطوات التأسيس",
                    "تنسيق الإجراءات مع الجهة المختصة داخل القابضة",
                    "متابعة الطلب حتى استكمال التأسيس",
                ],
                "en": [
                    "Review of the desired activity and partner structure",
                    "A clear explanation of the local requirements and formation steps",
                    "Coordination with the responsible team inside the Holding",
                    "Follow-up on the request until formation is complete",
                ],
            },
            "steps": {
                "ar": [
                    ("اختر البحرين", "حدّد أن السوق المقصود هو مملكة البحرين."),
                    ("أكمل النموذج", "بياناتك والنشاط وعدد الشركاء ونوع المستثمر."),
                    ("نتولى التوجيه", "يوجّه طلبك داخليًا إلى الجهة المختصة بالبحرين."),
                    ("المتابعة", "نتواصل معك لاستكمال المتطلبات حتى التأسيس."),
                ],
                "en": [
                    ("Choose Bahrain", "Confirm the Kingdom of Bahrain as your target market."),
                    ("Complete the form", "Your details, the activity, the number of partners and the investor type."),
                    ("We route it", "Your request is routed internally to the Bahrain team."),
                    ("Follow-up", "We contact you to complete the requirements through to formation."),
                ],
            },
            "faq": {
                "ar": [
                    ("هل يجب أن أكون مقيمًا في البحرين للتأسيس؟",
                     "تتيح مملكة البحرين التأسيس للمستثمرين المحليين والأجانب وفق النشاط. نراجع حالتك ونوضح المتطلبات المناسبة."),
                    ("هل يمكن أن يكون أحد الشركاء شركة؟",
                     "نعم، يمكن أن يكون الشريك فردًا أو شركة. أخبرنا بذلك في النموذج لنراعي الهيكل المناسب."),
                    ("هل أحتاج عنوانًا أو مكتبًا؟",
                     "يعتمد ذلك على النشاط. يمكنك تحديد احتياجك في النموذج وسنوضح الخيارات المتاحة."),
                ],
                "en": [
                    ("Do I need to reside in Bahrain to incorporate?",
                     "The Kingdom of Bahrain allows incorporation for local and foreign investors depending on the activity. We review your case and explain the requirements."),
                    ("Can a partner be a company?",
                     "Yes, a partner can be an individual or a company. Tell us in the form so we account for the right structure."),
                    ("Do I need an address or office?",
                     "This depends on the activity. You can indicate your need in the form and we will explain the available options."),
                ],
            },
        },
        "saudi": {
            "meta": {
                "ar": {
                    "title": "تأسيس شركة في السعودية",
                    "description": "تأسيس شركتك في المملكة العربية السعودية: النشاط، نوع المستثمر، الكيان والمدينة المستهدفة، بطلب واحد.",
                },
                "en": {
                    "title": "Company Formation in Saudi Arabia",
                    "description": "Set up your company in Saudi Arabia: activity, investor type, legal entity and target city, in one request.",
                },
            },
            "intro": {
                "ar": "نساعدك على تأسيس شركتك في المملكة العربية السعودية حسب نوع المستثمر والكيان والمدينة المستهدفة.",
                "en": "We help you form your company in Saudi Arabia according to the investor type, the entity and your target city.",
            },
            "highlights": {
                "ar": [
                    "مسارات متعددة للمستثمر المحلي والأجنبي",
                    "خيارات للكيان القانوني بحسب النشاط",
                    "مدن رئيسية ذات أولويات اقتصادية واضحة",
                ],
                "en": [
                    "Multiple paths for local and foreign investors",
                    "Legal-entity options according to the activity",
                    "Major cities with clear economic priorities",
                ],
            },
            "deliverables": {
                "ar": [
                    "مراجعة النشاط والمدينة المستهدفة",
                    "توضيح نوع المستثمر والكيان المناسب",
                    "تنسيق الإجراءات مع الجهة المختصة بالسعودية",
                    "متابعة الطلب حتى استكمال التأسيس",
                ],
                "en": [
                    "Review of the activity and the target city",
                    "Clarification of the investor type and the suitable entity",
                    "Coordination with the Saudi team inside the Holding",
                    "Follow-up on the request until formation is complete",
                ],
            },
            "steps": {
                "ar": [
                    ("اختر السعودية", "حدّد المملكة العربية السعودية كسوق مستهدف."),
                    ("أكمل النموذج", "النشاط ونوع المستثمر والكيان والمدينة."),
                    ("نتولى التوجيه", "يوجّه طلبك داخليًا إلى الجهة المختصة بالسعودية."),
                    ("المتابعة", "نتواصل معك لاستكمال المتطلبات حتى التأسيس."),
                ],
                "en": [
                    ("Choose Saudi Arabia", "Confirm Saudi Arabia as your target market."),
                    ("Complete the form", "The activity, investor type, entity and city."),
                    ("We route it", "Your request is routed internally to the Saudi team."),
                    ("Follow-up", "We contact you to complete the requirements through to formation."),
                ],
            },
            "faq": {
                "ar": [
                    ("هل يمكن للمستثمر الأجنبي التأسيس في السعودية؟",
                     "توجد مسارات للمستثمر المحلي والأجنبي بحسب النشاط. نراجع حالتك ونوضح المسار المناسب."),
                    ("هل يجب تحديد المدينة مسبقًا؟",
                     "نعم، المدينة المستهدفة تساعدنا على توضيح المتطلبات المحلية. يمكنك تحديدها في النموذج."),
                    ("ماذا يعني نوع الكيان؟",
                     "هو الشكل القانوني للشركة. إن لم تكن متأكدًا، اتركه وسنقترح الخيار المناسب لنشاطك."),
                ],
                "en": [
                    ("Can a foreign investor incorporate in Saudi Arabia?",
                     "There are paths for local and foreign investors depending on the activity. We review your case and explain the suitable path."),
                    ("Do I have to choose a city in advance?",
                     "Yes, the target city helps us explain the local requirements. You can specify it in the form."),
                    ("What is the legal entity?",
                     "It is the legal form of the company. If you are unsure, leave it and we will suggest the option that suits your activity."),
                ],
            },
        },
    },
    "feasibility-study": {
        "bahrain": {
            "meta": {
                "ar": {
                    "title": "دراسة جدوى في البحرين",
                    "description": "اطلب دراسة جدوى لمشروعك في مملكة البحرين: الفكرة، القطاع، الموقع ورأس المال التقريبي، بطلب واحد.",
                },
                "en": {
                    "title": "Feasibility Study in Bahrain",
                    "description": "Commission a feasibility study for your project in the Kingdom of Bahrain: idea, sector, location and approximate capital, in one request.",
                },
            },
            "intro": {
                "ar": "اطلب دراسة جدوى لمشروعك في مملكة البحرين، جديدة أو قائمة، وحدّد نوع الدراسة التي تحتاجها.",
                "en": "Commission a feasibility study for your project in the Kingdom of Bahrain, new or existing, and specify the type of study you need.",
            },
            "highlights": {
                "ar": [
                    "دراسات حسب نوع المشروع: جديد أو قائم",
                    "أنواع دراسة متعددة: جدوى، سوق، مالية أو فنية",
                    "مراعاة موقع المشروع إن وُجد",
                ],
                "en": [
                    "Studies by project stage: new or existing",
                    "Several study types: feasibility, market, financial or technical",
                    "Consideration of the project location where it exists",
                ],
            },
            "deliverables": {
                "ar": [
                    "توضيح نطاق الدراسة المطلوبة",
                    "مراجعة فكرة المشروع والقطاع",
                    "تنسيق الدراسة مع الجهة المختصة",
                    "تسليم الدراسة ومتابعة النتائج",
                ],
                "en": [
                    "A clear scope for the requested study",
                    "Review of the project idea and sector",
                    "Coordination of the study with the responsible team",
                    "Delivery of the study and follow-up on the results",
                ],
            },
            "steps": {
                "ar": [
                    ("اختر البحرين", "حدّد مملكة البحرين كسوق للدراسة."),
                    ("صف مشروعك", "الفكرة والقطاع والموقع ورأس المال التقريبي."),
                    ("حدّد نوع الدراسة", "جدوى أو سوق أو مالية أو فنية."),
                    ("النتيجة", "نعد الدراسة ونسلّمها مع المتابعة."),
                ],
                "en": [
                    ("Choose Bahrain", "Confirm the Kingdom of Bahrain as the study market."),
                    ("Describe your project", "The idea, sector, location and approximate capital."),
                    ("Choose the study type", "Feasibility, market, financial or technical."),
                    ("Result", "We prepare and deliver the study with follow-up."),
                ],
            },
            "faq": {
                "ar": [
                    ("هل الدراسة مناسبة لمشروع جديد؟",
                     "نعم، نوضح في النموذج ما إذا كان المشروع جديدًا أو قائمًا لتكييف الدراسة."),
                    ("ما نوع الدراسة التي أحتاجها؟",
                     "يعتمد على هدفك. إن لم تكن متأكدًا، اختر دراسة الجدوى وسنوضح الأنسب."),
                    ("هل يمكن دراسة مشروع بموقع محدد؟",
                     "نعم، يمكنك ذكر موقع المشروع إن وُجد لنراعي العوامل المحلية."),
                ],
                "en": [
                    ("Is the study suitable for a new project?",
                     "Yes. The form records whether the project is new or existing so the study can be adapted."),
                    ("Which study type do I need?",
                     "It depends on your goal. If unsure, choose feasibility and we will clarify the best fit."),
                    ("Can a project with a specific location be studied?",
                     "Yes. You can mention the project location, if any, so we account for local factors."),
                ],
            },
        },
        "saudi": {
            "meta": {
                "ar": {
                    "title": "دراسة جدوى في السعودية",
                    "description": "اطلب دراسة جدوى لمشروعك في المملكة العربية السعودية: الفكرة، القطاع، المدينة ورأس المال التقريبي، بطلب واحد.",
                },
                "en": {
                    "title": "Feasibility Study in Saudi Arabia",
                    "description": "Commission a feasibility study for your project in Saudi Arabia: idea, sector, city and approximate capital, in one request.",
                },
            },
            "intro": {
                "ar": "اطلب دراسة جدوى لمشروعك في المملكة العربية السعودية وحدّد المدينة المستهدفة ونوع الدراسة المطلوبة.",
                "en": "Commission a feasibility study for your project in Saudi Arabia and specify the target city and the type of study required.",
            },
            "highlights": {
                "ar": [
                    "دراسة تراعي المدينة المستهدفة",
                    "أنواع دراسة متعددة: جدوى، سوق، مالية أو فنية",
                    "مناسبة للمشاريع الجديدة والقائمة",
                ],
                "en": [
                    "A study that accounts for the target city",
                    "Several study types: feasibility, market, financial or technical",
                    "Suitable for new and existing projects",
                ],
            },
            "deliverables": {
                "ar": [
                    "توضيح نطاق الدراسة المطلوبة",
                    "مراجعة فكرة المشروع والقطاع والمدينة",
                    "تنسيق الدراسة مع الجهة المختصة",
                    "تسليم الدراسة ومتابعة النتائج",
                ],
                "en": [
                    "A clear scope for the requested study",
                    "Review of the project idea, sector and city",
                    "Coordination of the study with the responsible team",
                    "Delivery of the study and follow-up on the results",
                ],
            },
            "steps": {
                "ar": [
                    ("اختر السعودية", "حدّد المملكة العربية السعودية كسوق للدراسة."),
                    ("صف مشروعك", "الفكرة والقطاع والمدينة ورأس المال التقريبي."),
                    ("حدّد نوع الدراسة", "جدوى أو سوق أو مالية أو فنية."),
                    ("النتيجة", "نعد الدراسة ونسلّمها مع المتابعة."),
                ],
                "en": [
                    ("Choose Saudi Arabia", "Confirm Saudi Arabia as the study market."),
                    ("Describe your project", "The idea, sector, city and approximate capital."),
                    ("Choose the study type", "Feasibility, market, financial or technical."),
                    ("Result", "We prepare and deliver the study with follow-up."),
                ],
            },
            "faq": {
                "ar": [
                    ("هل يجب تحديد المدينة المستهدفة؟",
                     "نعم، المدينة تساعدنا على توضيح العوامل المحلية وأولويات السوق."),
                    ("هل تشمل الدراسة القطاع؟",
                     "نعم، نراجع القطاع ضمن نطاق الدراسة المطلوبة."),
                    ("هل يمكن دراسة مشروع قائم؟",
                     "نعم، نوضح في النموذج ما إذا كان المشروع جديدًا أو قائمًا."),
                ],
                "en": [
                    ("Do I have to specify the target city?",
                     "Yes. The city helps us explain the local factors and market priorities."),
                    ("Does the study cover the sector?",
                     "Yes. We review the sector as part of the requested study scope."),
                    ("Can an existing project be studied?",
                     "Yes. The form records whether the project is new or existing."),
                ],
            },
        },
    },
    "opportunities": {
        "bahrain": {
            "meta": {
                "ar": {
                    "title": "مشاريع وفرص للبيع في البحرين",
                    "description": "استعرض فرصًا ومشاريع للبيع أو الشراكة في مملكة البحرين. التفاصيل الحساسة تُشارك بعد تسجيل الاهتمام.",
                },
                "en": {
                    "title": "Projects & Opportunities for Sale in Bahrain",
                    "description": "Browse businesses and projects for sale or partnership in the Kingdom of Bahrain. Sensitive details are shared after interest is registered.",
                },
            },
            "intro": {
                "ar": "فرص ومشاريع في مملكة البحرين. نعرض معلومات مختصرة، ونشارك التفاصيل الحساسة بعد تسجيل اهتمامك ومراجعة الطرف المختص.",
                "en": "Businesses and projects in the Kingdom of Bahrain. We show a short summary and share sensitive details after your interest is registered and reviewed by the responsible party.",
            },
            "highlights": {
                "ar": [
                    "فرص في قطاعات متعددة داخل البحرين",
                    "أنواع متعددة: بيع كامل، بيع حصة، شريك استراتيجي أو استثمار",
                    "معلومات مختصرة فقط حتى تسجيل الاهتمام",
                ],
                "en": [
                    "Opportunities across several sectors within Bahrain",
                    "Several types: full sale, partial sale, strategic partner or investment",
                    "Summary information only until interest is registered",
                ],
            },
            "deliverables": {
                "ar": [
                    "استعراض الفرص المنشورة في هذا السوق",
                    "تسجيل اهتمامك بفرصة محددة",
                    "مراجعة الطرف المختص لطلبك",
                    "مشاركة التفاصيل بعد المراجعة",
                ],
                "en": [
                    "Browse the listings published in this market",
                    "Register your interest in a specific opportunity",
                    "Review of your request by the responsible party",
                    "Sharing of the details after review",
                ],
            },
            "steps": {
                "ar": [
                    ("استعرض الفرص", "شاهد الفرص المنشورة في البحرين."),
                    ("أبدِ اهتمامك", "اختر الفرصة التي تهمك."),
                    ("نسجّل طلبك", "يُسجَّل الاهتمام ويُوجَّه داخليًا."),
                    ("النتيجة", "تتولى الجهة المختصة المتابعة."),
                ],
                "en": [
                    ("Browse opportunities", "See the listings published in Bahrain."),
                    ("Register interest", "Choose the opportunity that interests you."),
                    ("We record it", "Your interest is recorded and routed internally."),
                    ("Result", "The responsible team handles the follow-up."),
                ],
            },
            "faq": {
                "ar": [
                    ("لماذا لا تظهر التفاصيل الكاملة؟",
                     "حفاظًا على سرية معلومات الأطراف. تُشارك التفاصيل بعد تسجيل الاهتمام ومراجعة الطرف المختص."),
                    ("كيف أسجّل اهتمامي؟",
                     "اختر الفرصة ثم أكمل نموذج الاهتمام؛ سيُسجَّل الطلب ضمن سوق البحرين تلقائيًا."),
                    ("هل كل الفرص منشورة؟",
                     "لا، تُعرض فقط الفرص التي وافقت الأطراف على نشر معلوماتها المختصرة."),
                ],
                "en": [
                    ("Why are the full details hidden?",
                     "To protect the confidentiality of the parties. Details are shared after interest is registered and reviewed."),
                    ("How do I register interest?",
                     "Choose an opportunity and complete the interest form; the request is recorded under the Bahrain market automatically."),
                    ("Are all opportunities published?",
                     "No. Only opportunities whose parties have agreed to publish a short summary are shown."),
                ],
            },
        },
        "saudi": {
            "meta": {
                "ar": {
                    "title": "مشاريع وفرص للبيع في السعودية",
                    "description": "استعرض فرصًا ومشاريع للبيع أو الشراكة في المملكة العربية السعودية. التفاصيل الحساسة تُشارك بعد تسجيل الاهتمام.",
                },
                "en": {
                    "title": "Projects & Opportunities for Sale in Saudi Arabia",
                    "description": "Browse businesses and projects for sale or partnership in Saudi Arabia. Sensitive details are shared after interest is registered.",
                },
            },
            "intro": {
                "ar": "فرص ومشاريع في المملكة العربية السعودية. نعرض معلومات مختصرة، ونشارك التفاصيل الحساسة بعد تسجيل اهتمامك ومراجعة الطرف المختص.",
                "en": "Businesses and projects in Saudi Arabia. We show a short summary and share sensitive details after your interest is registered and reviewed by the responsible party.",
            },
            "highlights": {
                "ar": [
                    "فرص في قطاعات متعددة داخل السوق السعودي",
                    "أنواع متعددة: بيع كامل، بيع حصة، شريك استراتيجي أو استثمار",
                    "معلومات مختصرة فقط حتى تسجيل الاهتمام",
                ],
                "en": [
                    "Opportunities across several sectors within the Saudi market",
                    "Several types: full sale, partial sale, strategic partner or investment",
                    "Summary information only until interest is registered",
                ],
            },
            "deliverables": {
                "ar": [
                    "استعراض الفرص المنشورة في هذا السوق",
                    "تسجيل اهتمامك بفرصة محددة",
                    "مراجعة الطرف المختص لطلبك",
                    "مشاركة التفاصيل بعد المراجعة",
                ],
                "en": [
                    "Browse the listings published in this market",
                    "Register your interest in a specific opportunity",
                    "Review of your request by the responsible party",
                    "Sharing of the details after review",
                ],
            },
            "steps": {
                "ar": [
                    ("استعرض الفرص", "شاهد الفرص المنشورة في السعودية."),
                    ("أبدِ اهتمامك", "اختر الفرصة التي تهمك."),
                    ("نسجّل طلبك", "يُسجَّل الاهتمام ويُوجَّه داخليًا."),
                    ("النتيجة", "تتولى الجهة المختصة المتابعة."),
                ],
                "en": [
                    ("Browse opportunities", "See the listings published in Saudi Arabia."),
                    ("Register interest", "Choose the opportunity that interests you."),
                    ("We record it", "Your interest is recorded and routed internally."),
                    ("Result", "The responsible team handles the follow-up."),
                ],
            },
            "faq": {
                "ar": [
                    ("لماذا لا تظهر التفاصيل الكاملة؟",
                     "حفاظًا على سرية معلومات الأطراف. تُشارك التفاصيل بعد تسجيل الاهتمام ومراجعة الطرف المختص."),
                    ("كيف أسجّل اهتمامي؟",
                     "اختر الفرصة ثم أكمل نموذج الاهتمام؛ سيُسجَّل الطلب ضمن السوق السعودي تلقائيًا."),
                    ("هل كل الفرص منشورة؟",
                     "لا، تُعرض فقط الفرص التي وافقت الأطراف على نشر معلوماتها المختصرة."),
                ],
                "en": [
                    ("Why are the full details hidden?",
                     "To protect the confidentiality of the parties. Details are shared after interest is registered and reviewed."),
                    ("How do I register interest?",
                     "Choose an opportunity and complete the interest form; the request is recorded under the Saudi market automatically."),
                    ("Are all opportunities published?",
                     "No. Only opportunities whose parties have agreed to publish a short summary are shown."),
                ],
            },
        },
    },
    "investment": {
        "bahrain": {
            "meta": {
                "ar": {
                    "title": "فرص استثمارية في البحرين",
                    "description": "فرص استثمارية وشراكات في مملكة البحرين عبر سفير القابضة، مع توجيه الطلب داخليًا ومتابعته.",
                },
                "en": {
                    "title": "Investment Opportunities in Bahrain",
                    "description": "Investment and partnership opportunities in the Kingdom of Bahrain with Safir Holding, routed internally and followed up.",
                },
            },
            "intro": {
                "ar": "فرص استثمارية وشراكات في مملكة البحرين. سجّل اهتمامك وسنوجّه طلبك إلى الجهة المختصة.",
                "en": "Investment and partnership opportunities in the Kingdom of Bahrain. Register your interest and we will route your request to the responsible team.",
            },
            "highlights": {
                "ar": [
                    "فرص استثمارية وشراكات في قطاعات متنوعة",
                    "مناسب للأفراد والشركات",
                    "متابعة مباشرة من الجهة المختصة",
                ],
                "en": [
                    "Investment and partnership opportunities across sectors",
                    "Suitable for individuals and companies",
                    "Direct follow-up by the responsible team",
                ],
            },
            "deliverables": {
                "ar": [
                    "استعراض الفرص الاستثمارية المتاحة",
                    "تسجيل ملفك واهتمامك",
                    "توجيه الطلب داخليًا",
                    "المتابعة حتى النتيجة",
                ],
                "en": [
                    "Browse the available investment opportunities",
                    "Register your profile and interest",
                    "Routing of the request internally",
                    "Follow-up through to an outcome",
                ],
            },
            "steps": {
                "ar": [
                    ("استعرض", "تعرّف على الفرص الاستثمارية."),
                    ("سجّل اهتمامك", "أكمل النموذج ببياناتك."),
                    ("التوجيه", "يوجّه الطلب إلى الجهة المختصة."),
                    ("المتابعة", "نتواصل معك حتى النتيجة."),
                ],
                "en": [
                    ("Browse", "Explore the investment opportunities."),
                    ("Register interest", "Complete the form with your details."),
                    ("Routing", "The request is routed to the responsible team."),
                    ("Follow-up", "We stay in touch through to an outcome."),
                ],
            },
            "faq": {
                "ar": [
                    ("هل الاستثمار متاح للأفراد؟",
                     "نعم، يمكن للأفراد والشركات تسجيل الاهتمام. نوضح المتطلبات حسب الحالة."),
                    ("ما الذي أحتاجه للتسجيل؟",
                     "بيانات التواصل ونبذة مختصرة عن ملفك الاستثماري."),
                    ("كيف تتم المتابعة؟",
                     "تتولى الجهة المختصة داخل القابضة التواصل معك لمتابعة التفاصيل."),
                ],
                "en": [
                    ("Is investing open to individuals?",
                     "Yes. Individuals and companies can register interest; we explain the requirements case by case."),
                    ("What do I need to register?",
                     "Your contact details and a short profile of your investment background."),
                    ("How is follow-up handled?",
                     "The responsible team inside the Holding contacts you to follow up on the details."),
                ],
            },
        },
        "saudi": {
            "meta": {
                "ar": {
                    "title": "فرص استثمارية في السعودية",
                    "description": "فرص استثمارية وشراكات في المملكة العربية السعودية عبر سفير القابضة، مع توجيه الطلب داخليًا ومتابعته.",
                },
                "en": {
                    "title": "Investment Opportunities in Saudi Arabia",
                    "description": "Investment and partnership opportunities in Saudi Arabia with Safir Holding, routed internally and followed up.",
                },
            },
            "intro": {
                "ar": "فرص استثمارية وشراكات في المملكة العربية السعودية. سجّل اهتمامك وسنوجّه طلبك إلى الجهة المختصة.",
                "en": "Investment and partnership opportunities in Saudi Arabia. Register your interest and we will route your request to the responsible team.",
            },
            "highlights": {
                "ar": [
                    "فرص استثمارية وشراكات في السوق السعودي",
                    "مناسب للأفراد والشركات",
                    "متابعة مباشرة من الجهة المختصة",
                ],
                "en": [
                    "Investment and partnership opportunities in the Saudi market",
                    "Suitable for individuals and companies",
                    "Direct follow-up by the responsible team",
                ],
            },
            "deliverables": {
                "ar": [
                    "استعراض الفرص الاستثمارية المتاحة",
                    "تسجيل ملفك واهتمامك",
                    "توجيه الطلب داخليًا",
                    "المتابعة حتى النتيجة",
                ],
                "en": [
                    "Browse the available investment opportunities",
                    "Register your profile and interest",
                    "Routing of the request internally",
                    "Follow-up through to an outcome",
                ],
            },
            "steps": {
                "ar": [
                    ("استعرض", "تعرّف على الفرص الاستثمارية."),
                    ("سجّل اهتمامك", "أكمل النموذج ببياناتك."),
                    ("التوجيه", "يوجّه الطلب إلى الجهة المختصة."),
                    ("المتابعة", "نتواصل معك حتى النتيجة."),
                ],
                "en": [
                    ("Browse", "Explore the investment opportunities."),
                    ("Register interest", "Complete the form with your details."),
                    ("Routing", "The request is routed to the responsible team."),
                    ("Follow-up", "We stay in touch through to an outcome."),
                ],
            },
            "faq": {
                "ar": [
                    ("هل الاستثمار متاح للأفراد؟",
                     "نعم، يمكن للأفراد والشركات تسجيل الاهتمام. نوضح المتطلبات حسب الحالة."),
                    ("ما الذي أحتاجه للتسجيل؟",
                     "بيانات التواصل ونبذة مختصرة عن ملفك الاستثماري."),
                    ("كيف تتم المتابعة؟",
                     "تتولى الجهة المختصة داخل القابضة التواصل معك لمتابعة التفاصيل."),
                ],
                "en": [
                    ("Is investing open to individuals?",
                     "Yes. Individuals and companies can register interest; we explain the requirements case by case."),
                    ("What do I need to register?",
                     "Your contact details and a short profile of your investment background."),
                    ("How is follow-up handled?",
                     "The responsible team inside the Holding contacts you to follow up on the details."),
                ],
            },
        },
    },
}


# Group companies shown for trust and credibility only. They are never the
# primary service navigation. Nothing here is invented: an entity is only added
# when verified, so the list is intentionally short and each entry is marked
# with its verification state for the internal review that will confirm it.
GROUP_COMPANIES: list[dict] = [
    {
        "code": "alam-damac",
        "name_ar": "مركز عالم داماك للأعمال",
        "name_en": "Alam Damac Business Centre",
        "country": "bahrain",
        "sector": {"ar": "خدمات أعمال", "en": "Business Services"},
        "description": {
            "ar": "مركز أعمال يقدم خدمات مؤسسية ودعمًا للشركات.",
            "en": "A business centre providing corporate services and company support.",
        },
        "verified": False,
    },
    {
        "code": "rukn-alriyada",
        "name_ar": "ركن الريادة",
        "name_en": "Rukn Al Riyada",
        "country": "bahrain",
        "sector": {"ar": "قانون", "en": "Legal"},
        "description": {
            "ar": "خدمات قانونية واستشارات للشركات والأفراد.",
            "en": "Legal services and consultancy for companies and individuals.",
        },
        "verified": False,
    },
    {
        "code": "damac-world",
        "name_ar": "داماك ورلد التجارية",
        "name_en": "Damac World Trading",
        "country": "bahrain",
        "sector": {"ar": "تجارة", "en": "Trading"},
        "description": {
            "ar": "أنشطة تجارية وتوريد ضمن المجموعة.",
            "en": "Trading and supply activities within the group.",
        },
        "verified": False,
    },
]

# Navigation. ``path`` is the canonical English route; ``path_ar`` is its
# Arabic mirror.
NAV: list[dict] = [
    {"key": "home", "path": "/", "path_ar": "/ar", "label": {"ar": "الرئيسية", "en": "Home"}},
    {
        "key": "opportunities",
        "path": "/opportunities",
        "path_ar": "/ar/الفرص-والمشاريع",
        "label": {"ar": "الفرص والمشاريع", "en": "Opportunities & Projects"},
    },
    {
        "key": "services",
        "path": "/services",
        "path_ar": "/ar/خدمات-الأعمال",
        "label": {"ar": "خدمات الأعمال", "en": "Business Services"},
    },
    {
        "key": "group",
        "path": "/group-companies",
        "path_ar": "/ar/شركات-المجموعة",
        "label": {"ar": "شركات المجموعة", "en": "Group Companies"},
    },
    {
        "key": "about",
        "path": "/about",
        "path_ar": "/ar/عن-القابضة",
        "label": {"ar": "عن القابضة", "en": "About SAFIR Holding"},
    },
    {
        "key": "contact",
        "path": "/contact",
        "path_ar": "/ar/تواصل",
        "label": {"ar": "تواصل", "en": "Contact"},
    },
]

# Top-level page keys and their localized paths, used by the router and sitemap.
PAGE_PATHS: dict[str, dict[str, str]] = {
    "home": {"ar": "/ar", "en": "/"},
    "opportunities": {"ar": "/ar/الفرص-والمشاريع", "en": "/opportunities"},
    "services": {"ar": "/ar/خدمات-الأعمال", "en": "/services"},
    "group": {"ar": "/ar/شركات-المجموعة", "en": "/group-companies"},
    "about": {"ar": "/ar/عن-القابضة", "en": "/about"},
    "contact": {"ar": "/ar/تواصل", "en": "/contact"},
    "list-your-business": {"ar": "/ar/اعرض-شركتك", "en": "/list-your-business"},
}


@dataclass
class PageMeta:
    """Everything the HTML shell needs for one page.

    Built once per page and consumed by both the renderer and the SEO module,
    so a page's title, description, canonical and structured data are defined
    together and cannot disagree.
    """

    route: str
    lang: str
    title: str
    description: str
    canonical_path: str
    alternates: dict[str, str] = field(default_factory=dict)
    robots: str = "index, follow"
    og_type: str = "website"
    breadcrumbs: list[tuple[str, str]] = field(default_factory=list)
    # Set only on market/service pages, so the SEO layer can emit a ``Service``
    # node and a ``FAQPage`` node without re-parsing the route string.
    market: str | None = None
    service_slug: str | None = None


def market_label(market: str, lang: str) -> str:
    return MARKET_LABELS.get(market, {}).get(lang, market)


def nav_label(key: str, lang: str) -> str:
    for item in NAV:
        if item["key"] == key:
            return item["label"][lang]
    return key


def market_slug(market: str, lang: str) -> str:
    return MARKET_SLUG_AR.get(market, market) if lang == "ar" else market


def service_def(slug: str) -> dict | None:
    return SERVICES.get(slug)


def localized_service_slug(slug: str, lang: str) -> str:
    service = SERVICES.get(slug)
    if not service:
        return slug
    return service["slug_ar"] if lang == "ar" else service["slug"]


def market_service_path(market: str, slug: str, lang: str) -> str:
    """The public path for a market/service page in the given language.

    Arabic pages live under ``/ar/<market-ar>/<service-ar>``; English pages
    under ``/<market>/<service>``. This keeps one canonical English URL per
    page and a genuine Arabic mirror, which is what the hreflang pair points
    at.
    """
    service_slug = localized_service_slug(slug, lang)
    if lang == "ar":
        return f"/ar/{market_slug(market, 'ar')}/{service_slug}"
    return f"/{market}/{service_slug}"


def service_market_content(slug: str, market: str) -> dict | None:
    """Per market+service page content, or ``None`` if not defined."""
    return SERVICE_MARKET_CONTENT.get(slug, {}).get(market)


def all_market_service_pages() -> list[tuple[str, str]]:
    """Every (market, service-slug) combination that has a real page."""
    return [(market, slug) for market in MARKETS for slug in SERVICES]
