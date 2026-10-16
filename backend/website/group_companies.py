"""Canonical group-company dataset - extracted verbatim from the approved
handoff (``content/companies.json``, Startup_Safeer_Developer_Handoff_v1).

This is the single source of truth for the group-companies experience. It is
generated from the handoff rather than typed by hand so the names, order and
copy match the approved package exactly. ``null`` means "not provided" and must
never be rendered as a value, a placeholder or a fake logo.
"""

from __future__ import annotations

# Ordered 1..9 exactly as approved in the handoff.
GROUP_COMPANIES: list[dict] = [{'id': 'alreyada',
  'order': 1,
  'name_ar': 'ركن الريادة للمحاماة والاستشارات القانونية',
  'name_en': 'ALREYADA CORNER LAW & LEGAL CONSULTANCY',
  'country_ar': 'مملكة البحرين',
  'country_en': 'Bahrain',
  'area_ar': 'الدبلوماسية',
  'area_en': 'Diplomatic Area',
  'phone': '+973 17595522',
  'email': 'info@alreyada-law.com',
  'whatsapp': None,
  'website': None,
  'logo': None,
  'about_ar': 'مكتب محاماة واستشارات قانونية في مملكة البحرين، يقدم المشورة القانونية '
              'ويمثّل العملاء في المنازعات والقضايا والإجراءات القانونية، وفق نطاق '
              'الترخيص المهني للمكتب.',
  'about_en': 'A Bahrain-based law and legal consultancy office providing legal advice '
              'and representing clients in disputes, cases and legal proceedings '
              'within the scope of its professional licence.',
  'services_ar': ['الاستشارات القانونية.',
                  'تمثيل العملاء في المنازعات والقضايا.',
                  'متابعة الإجراءات القانونية ذات الصلة.'],
  'services_en': ['Legal advice.',
                  'Representation in disputes and cases.',
                  'Handling related legal procedures.'],
  'card_ar': 'خدمات واستشارات قانونية وتمثيل العملاء في المنازعات والقضايا والإجراءات '
             'القانونية.',
  'card_en': 'Legal advice and services, with client representation in disputes, cases '
             'and legal proceedings.',
  'country': 'bahrain'},
 {'id': 'damac-business',
  'order': 2,
  'name_ar': 'مركز عالم داماك للأعمال ذ.م.م',
  'name_en': 'DAMAC WORLD BUSINESS CENTER W.L.L',
  'country_ar': 'مملكة البحرين',
  'country_en': 'Bahrain',
  'area_ar': 'السيف',
  'area_en': 'Seef',
  'phone': '+973 17826990',
  'email': 'info@dwbc-bh.com',
  'whatsapp': None,
  'website': None,
  'logo': None,
  'about_ar': 'شركة متخصصة في خدمات الأعمال في مملكة البحرين، تدعم الشركات والمستثمرين '
              'في تأسيس أعمالهم ومتابعة معاملاتهم الحكومية واحتياجاتهم الإدارية.',
  'about_en': 'A business services company in Bahrain supporting companies and '
              'investors with business establishment, government transactions and '
              'administrative needs.',
  'services_ar': ['تأسيس الشركات.',
                  'متابعة وتخليص المعاملات الحكومية.',
                  'الخدمات الإدارية المساندة للشركات والمستثمرين.'],
  'services_en': ['Company formation.',
                  'Government transaction processing and follow-up.',
                  'Administrative support for companies and investors.'],
  'card_ar': 'تأسيس الشركات، ومتابعة وتخليص المعاملات الحكومية، وتقديم الخدمات '
             'الإدارية المساندة للشركات والمستثمرين.',
  'card_en': 'Company formation, government transaction processing and administrative '
             'support for companies and investors.',
  'country': 'bahrain'},
 {'id': 'damac-trading',
  'order': 3,
  'name_ar': 'داماك ورلد التجارية ذ.م.م',
  'name_en': 'DAMAC WORLD TRADING W.L.L',
  'country_ar': 'مملكة البحرين',
  'country_en': 'Bahrain',
  'area_ar': 'السنابس',
  'area_en': 'Sanabis',
  'phone': '+973 37088373',
  'email': 'info@damacgr.com',
  'whatsapp': None,
  'website': None,
  'logo': None,
  'about_ar': 'شركة تجارية متخصصة في تجارة وتوزيع المواد الغذائية والمكملات الغذائية '
              'بالجملة، وتعمل على تطوير قنوات التوريد والتوزيع للمنتجات التي تتعامل '
              'بها.',
  'about_en': 'A trading company specialising in the wholesale supply and distribution '
              'of food products and dietary supplements, with a focus on developing '
              'supply and distribution channels for its products.',
  'services_ar': ['تجارة المواد الغذائية بالجملة.',
                  'تجارة المكملات الغذائية بالجملة.',
                  'توريد المنتجات وتوزيعها وتطوير قنوات وصولها إلى الأسواق.'],
  'services_en': ['Wholesale food trading.',
                  'Wholesale dietary supplement trading.',
                  'Product supply, distribution and development of routes to market.'],
  'card_ar': 'تجارة وتوزيع المواد الغذائية والمكملات الغذائية بالجملة، وتطوير قنوات '
             'التوريد والتوزيع.',
  'card_en': 'Wholesale trading and distribution of food products and dietary '
             'supplements, with development of supply and distribution channels.',
  'country': 'bahrain'},
 {'id': 'bait-al-rayhan',
  'order': 4,
  'name_ar': 'شركة بيت الريحان التجارية ذ.م.م',
  'name_en': 'BAIT AL RAYHAN TRADING COMPANY W.L.L',
  'country_ar': 'مملكة البحرين',
  'country_en': 'Bahrain',
  'area_ar': 'السنابس',
  'area_en': 'Sanabis',
  'phone': '+973 17001555',
  'email': 'info@bait-alrayhan.com',
  'whatsapp': None,
  'website': None,
  'logo': None,
  'about_ar': 'شركة تجارة إلكترونية متخصصة في بيع المكملات الغذائية ومنتجات العناية '
              'والتجميل للمستهلكين عبر قنوات البيع الإلكترونية.',
  'about_en': 'An e-commerce company selling dietary supplements, personal care and '
              'beauty products directly to consumers through online sales channels.',
  'services_ar': ['المكملات الغذائية.', 'منتجات العناية.', 'منتجات التجميل.'],
  'services_en': ['Dietary supplements.',
                  'Personal care products.',
                  'Beauty products.'],
  'card_ar': 'بيع المكملات الغذائية ومنتجات العناية والتجميل للمستهلكين عبر قنوات '
             'التجارة الإلكترونية.',
  'card_en': 'Online sales of dietary supplements, personal care and beauty products '
             'to consumers.',
  'country': 'bahrain'},
 {'id': 'digital-rocket',
  'order': 5,
  'name_ar': 'ديجيتال روكيت للدعاية والإعلان ذ.م.م',
  'name_en': 'DIGITAL ROCKET FOR ADVERTISING W.L.L',
  'country_ar': 'مملكة البحرين',
  'country_en': 'Bahrain',
  'area_ar': 'الدبلوماسية',
  'area_en': 'Diplomatic Area',
  'phone': '+973 39848990',
  'email': 'info@dr-bh.com',
  'whatsapp': None,
  'website': None,
  'logo': None,
  'about_ar': 'شركة متخصصة في الدعاية والإعلان والتسويق والحلول الرقمية، تساعد الشركات '
              'والعلامات التجارية على تطوير حضورها التسويقي والرقمي والوصول إلى '
              'عملائها.',
  'about_en': 'An advertising, marketing and digital solutions company helping '
              'businesses and brands strengthen their marketing and digital presence '
              'and reach their customers.',
  'services_ar': ['الدعاية والإعلان.',
                  'التسويق.',
                  'الحلول الرقمية الداعمة للحضور التسويقي.'],
  'services_en': ['Advertising.',
                  'Marketing.',
                  'Digital solutions supporting marketing presence.'],
  'card_ar': 'خدمات الدعاية والإعلان والتسويق والحلول الرقمية، لتطوير حضور الشركات '
             'والعلامات التجارية والوصول إلى عملائها.',
  'card_en': 'Advertising, marketing and digital solutions to strengthen the presence '
             'of businesses and brands and reach their customers.',
  'country': 'bahrain'},
 {'id': 'najmat-business',
  'order': 6,
  'name_ar': 'نجمة الأعمال للخدمات التجارية – الأعمال',
  'name_en': 'Najmat Al Aamal for Commercial Services – Business',
  'country_ar': 'المملكة العربية السعودية',
  'country_en': 'Saudi Arabia',
  'area_ar': 'الرياض',
  'area_en': 'Riyadh',
  'phone': None,
  'email': None,
  'whatsapp': None,
  'website': None,
  'logo': None,
  'about_ar': 'منشأة متخصصة في خدمات تأسيس الشركات ودعم المستثمرين في المملكة العربية '
              'السعودية، ومتابعة وتعقيب المعاملات التجارية والحكومية.',
  'about_en': 'A business services establishment supporting company formation and '
              'investors in Saudi Arabia, including the processing and follow-up of '
              'commercial and government transactions.',
  'services_ar': ['تأسيس الشركات.',
                  'خدمات دعم المستثمرين.',
                  'متابعة وتعقيب المعاملات التجارية والحكومية.'],
  'services_en': ['Company formation.',
                  'Investor support services.',
                  'Commercial and government transaction processing and follow-up.'],
  'card_ar': 'تأسيس الشركات ودعم المستثمرين، ومتابعة وتعقيب المعاملات التجارية '
             'والحكومية.',
  'card_en': 'Company formation, investor support, and commercial and government '
             'transaction processing and follow-up.',
  'country': 'saudi'},
 {'id': 'wealth-first',
  'order': 7,
  'name_ar': 'ويلث فيرست للاستشارات الإدارية',
  'name_en': 'WEALTH FIRST MANAGEMENT CONSULTANCY',
  'country_ar': 'مملكة البحرين',
  'country_en': 'Bahrain',
  'area_ar': 'السيف',
  'area_en': 'Seef',
  'phone': '+973 39808990',
  'email': 'info@wealthfirst-bh.com',
  'whatsapp': None,
  'website': None,
  'logo': None,
  'about_ar': 'شركة استشارات إدارية تقدم دراسات الجدوى وخطط الأعمال والاستشارات '
              'المرتبطة بتطوير المشاريع، وتساعد في دراسة وترتيب الحلول التمويلية '
              'المناسبة للأعمال ضمن نطاق خدماتها.',
  'about_en': 'A management consultancy providing feasibility studies, business plans '
              'and advice on business development, with assistance in assessing and '
              'arranging suitable financing solutions within the scope of its '
              'services.',
  'services_ar': ['دراسات الجدوى وخطط الأعمال.',
                  'الاستشارات الإدارية وتطوير الأعمال.',
                  'المساعدة في دراسة وترتيب الحلول التمويلية المناسبة للمشاريع.'],
  'services_en': ['Feasibility studies and business plans.',
                  'Management consultancy and business development.',
                  'Assistance in assessing and arranging suitable business financing '
                  'solutions.'],
  'card_ar': 'دراسات الجدوى وخطط الأعمال والاستشارات الإدارية لتطوير المشاريع، '
             'والمساعدة في دراسة وترتيب الحلول التمويلية المناسبة للأعمال.',
  'card_en': 'Feasibility studies, business plans and management consultancy for '
             'business development, with assistance in assessing and arranging '
             'suitable financing solutions.',
  'country': 'bahrain'},
 {'id': 'najmat-contracting',
  'order': 8,
  'name_ar': 'نجمة الأعمال للخدمات التجارية – المقاولات',
  'name_en': 'Najmat Al Aamal for Commercial Services – Contracting',
  'country_ar': 'المملكة العربية السعودية',
  'country_en': 'Saudi Arabia',
  'area_ar': 'الرياض',
  'area_en': 'Riyadh',
  'phone': '+966 50 568 8912',
  'email': 'info@najmat-sa.com',
  'whatsapp': None,
  'website': None,
  'logo': None,
  'about_ar': 'منشأة تعمل في قطاع المقاولات والتشطيبات والأعمال الفنية والخدمات '
              'التقنية المرتبطة بالمشاريع، وتقدم حلولًا للأفراد والشركات من مرحلة '
              'التخطيط وحتى تنفيذ الأعمال.',
  'about_en': 'An establishment providing contracting, fit-out, technical works and '
              'project-related technology services for individuals and businesses, '
              'from planning through execution.',
  'services_ar': ['المقاولات والتشطيبات.',
                  'الأعمال الفنية.',
                  'الخدمات التقنية المرتبطة بالمشاريع.'],
  'services_en': ['Contracting and fit-out works.',
                  'Technical works.',
                  'Project-related technology services.'],
  'card_ar': 'خدمات المقاولات والتشطيبات والأعمال الفنية والحلول التقنية المرتبطة '
             'بالمشاريع، من التخطيط إلى التنفيذ.',
  'card_en': 'Contracting, fit-out, technical works and project-related technology '
             'solutions, from planning to execution.',
  'country': 'saudi'},
 {'id': 'allamasat',
  'order': 9,
  'name_ar': 'اللمسات الفنية للاتصالات',
  'name_en': None,
  'country_ar': 'المملكة العربية السعودية',
  'country_en': 'Saudi Arabia',
  'area_ar': 'الخبر',
  'area_en': 'Al Khobar',
  'phone': None,
  'email': None,
  'whatsapp': None,
  'website': None,
  'logo': None,
  'about_ar': 'منشأة سعودية تعمل في قطاع خدمات الاتصالات والتقنية، وتشمل أنشطتها توزيع '
              'وبيع بعض خدمات وحلول هواوي، وخدمات التخزين السحابي، وخدمات الرسائل '
              'القصيرة للأعمال وفق التراخيص والأنشطة المعتمدة.',
  'about_en': 'A Saudi establishment in telecommunications and technology services. '
              'Its activities include the distribution and sale of selected Huawei '
              'services and solutions, cloud storage and business SMS services, '
              'subject to approved licences and activities.',
  'services_ar': ['توزيع وبيع بعض خدمات وحلول هواوي.',
                  'خدمات التخزين السحابي.',
                  'خدمات الرسائل القصيرة للأعمال وفق التراخيص المعتمدة.'],
  'services_en': ['Distribution and sale of selected Huawei services and solutions.',
                  'Cloud storage services.',
                  'Business SMS services under approved licences.'],
  'card_ar': 'خدمات وحلول الاتصالات والتقنية، تشمل التخزين السحابي وبعض خدمات وحلول '
             'هواوي، وخدمات الرسائل القصيرة للأعمال وفق التراخيص المعتمدة.',
  'card_en': 'Telecommunications and technology services, including cloud storage, '
             'selected Huawei services and solutions, and business SMS under approved '
             'licences.',
  'country': 'saudi'}]

def ordered() -> list[dict]:
    """Companies in the approved order (1..9)."""
    return sorted(GROUP_COMPANIES, key=lambda c: c["order"])
