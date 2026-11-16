# B2B and Adjacent-Market Monetization for Vantage's Pedestrian-Hazard CV Model

Research date: 2026-11-16. Tool budget limited this pass to ~15 searches/scrapes; many pricing items are not public (vendors use "contact sales"), and those are flagged as gaps rather than estimated.

## 1. Ultralytics AGPL-3.0 licensing: what Vantage must do to sell/license a YOLO11-based model (blocking issue for all B2B paths)

### Takeaway
Any closed-source commercial use of Vantage's YOLO11n model (licensing the model/SDK, embedding it in OEM hardware, offering a cloud API, even internal private business tools) needs an Ultralytics Enterprise License. Ultralytics says custom-trained weights are also AGPL by default, and it does not publish the license price. The other option is to retrain on a permissively licensed architecture that already runs on IMX500 (NanoDet-Plus Apache-2.0, EfficientDet-Lite0 Apache-2.0, SSD MobileNetV2 FPN-Lite MIT).

### Cited Findings
- Ultralytics: complying with AGPL-3.0 means publicly releasing "the complete corresponding source code for the entire derivative work, including the larger application, modifications, scripts, configuration files, and, where applicable, model weights." If you do not want to open-source the project, you need an Enterprise License. — [Ultralytics License](https://www.ultralytics.com/license)
- Ultralytics lists cases that need an Enterprise License: internal business tools; any commercial product or service; proprietary software; "SaaS platforms, APIs, or cloud systems that use YOLO behind the scenes"; "embedded deployments in hardware, edge devices, robotics, cameras, or appliances"; and "using custom-trained or fine-tuned YOLO models in a proprietary or commercial setting." — [Ultralytics License](https://www.ultralytics.com/license)
- Ultralytics says all YOLO models trained with its code fall under AGPL-3.0 by default, because the license covers the training code and the models it produces. — [Ultralytics License](https://www.ultralytics.com/license)
- The Enterprise License covers the whole Ultralytics YOLO portfolio, including YOLO26, earlier versions and future models released during the term. Pricing is not listed: it is "tailored to each organization's size and specific use case," and you get a quote through a request form. — [Ultralytics License](https://www.ultralytics.com/license)
- Ultralytics Platform pricing as of Nov 2026: Free costs $0 with $25 of one-time credits and is AGPL-3.0. Pro costs $29 per seat per month, is AGPL-3.0 and allows up to 5 members. Enterprise is "Custom" and is the only tier that includes the Ultralytics Enterprise License (it also adds SSO, a HIPAA BAA and on-prem). — [Ultralytics Pricing](https://www.ultralytics.com/pricing)
- Ultralytics staff say the Enterprise License pricing "could be a one-time fee, a subscription model, or a custom" arrangement depending on scope. — [GitHub discussion #7440](https://github.com/orgs/ultralytics/discussions/7440)
- Anecdotal and unverified: a Reddit user reported a quote of $5,000/year for an enterprise license for a company of 1–19 employees; another said it was "more than 20k USD per year." — [Reddit r/computervision](https://www.reddit.com/r/computervision/comments/1eaxwea/using_yolo_from_ultralyrics_for_business_use_case/) (thread dates from about 2024, so treat these figures as old and anecdotal)
- Roboflow summarizes it the same way: YOLO11 is AGPL-3.0, and private commercial use requires an agreement with Ultralytics. — [Roboflow YOLO11 license page](https://roboflow.com/model-licenses/yolo11)
- The official Raspberry Pi AI Camera (IMX500) model zoo lists these licenses: YOLO11n is AGPL-3.0, YOLOv8n is AGPL-3.0, EfficientDet Lite-0 is Apache 2.0, NanoDet-Plus is Apache 2.0, and SSD MobileNetV2 FPN Lite is MIT. — [raspberrypi/imx500-models](https://github.com/raspberrypi/imx500-models)
- Roboflow notes that some models need an extra license for commercial self-hosting; for example RF-DETR 2XL needs a paid add-on. — [Roboflow Pricing](https://roboflow.com/pricing)

### Inferences
- The custom 29-class weights are probably AGPL-encumbered by Ultralytics' reading. Licensing them to an OEM, or running them behind a closed API, without an Enterprise License creates legal risk, and OEM due diligence would likely catch it.
- The fastest legal route to revenue is one of these:
  - (a) Get a quote now. Startup quotes appear to be around $5k/yr, but that is anecdotal.
  - (b) Retrain the same labelled dataset on NanoDet-Plus or SSD MobileNetV2 FPN-Lite. Both are already proven on IMX500 in the official zoo, are Apache/MIT licensed, and need no Ultralytics dependency.
  - (c) Open-source the full stack under AGPL and sell services, data or hardware around it.
- Vantage's own labelled data is a separate asset. The license on the data depends on the source datasets, not on Ultralytics.

### Gaps
- No official Ultralytics price. The only figures are anecdotal and roughly 2024.
- This pass did not confirm that RT-DETR, D-FINE, RF-DETR, YOLOX or DEIM convert to IMX500. Transformer detectors are likely a poor fit for the IMX500's memory budget (about 8 MB), but no source was verified, so treat that as unconfirmed.
- Not covered: COCO/Flickr image terms, ROD dataset terms, and whether a model trained on CC-BY data carries attribution duties.

## 2. Licensing an SDK/model to assistive device and smart-glasses makers; CV-platform price benchmarks

### Takeaway
Smart-glasses camera access is opening up: Meta's Wearables Device Access Toolkit gives phone apps the camera and audio from Ray-Ban Meta glasses. No public revenue-share or royalty terms were found. Public CV-platform prices give a floor for what an SDK license is worth, but per-device royalty rates are almost never published.

### Cited Findings
- Meta Wearables Device Access Toolkit: developers can access the camera and audio of Meta AI glasses to extend their mobile apps. HumanWare, which makes blindness products, is named as an early partner. — [Meta developer blog](https://developers.meta.com/blog/introducing-meta-wearables-device-access-toolkit/)
- Supported devices: Ray-Ban Meta Gen 1 and Gen 2, and Meta Ray-Ban Display. Capabilities: video streaming, photo capture, microphone and audio into iOS and Android apps. — [Meta Wearables FAQ](https://developers.meta.com/wearables/faq/); [Reddit summary](https://www.reddit.com/r/augmentedreality/comments/1nkpkhg/introducing_the_meta_wearables_device_access/)
- The Android SDK is marked "in developer preview." — [GitHub meta/meta-wearables-dat-android](https://github.com/meta/meta-wearables-dat-android)
- Smart-cane precedent: WeWALK Smart Cane 2 already ships "obstacle detection," voice navigation and AI assistance, and was on Forbes' Accessibility 100 (2025) and Accessibility 200 (2026) lists. — [WeWALK](https://wewalk.io/en/); [WeWALK news](https://wewalk.io/en/wewalk-in-the-news/)
- Benchmark: Edge Impulse Professional plan "as low as $400 per month." Full commercial rights require the Enterprise plan. — [Edge Impulse blog](https://www.edgeimpulse.com/blog/announcing-professional-plan/); Enterprise price is not public ([Edge Impulse pricing](https://www.edgeimpulse.com/pricing))
- Benchmark: Roboflow Enterprise is custom-priced. Commercial self-hosted (edge) use is an Enterprise add-on, and self-hosted inference uses 1 credit per 3,000 images or 500 minutes of video per camera per month. — [Roboflow Licensing](https://roboflow.com/licensing); [checkthat.ai summary of Roboflow pricing 2026](https://checkthat.ai/brands/roboflow/pricing) (aggregator)
- Sony AITRIOS is Sony's IMX500 edge-AI platform. It has a marketplace where third parties list tools, e.g. Neurala Brain Builder. — [AITRIOS](https://www.aitrios.sony-semicon.com/); [Neurala press release](https://www.neurala.com/news/press-releases/neurala-announces-availability-of-brain-builder-on-sonys-aitrios-marketplace/)

### Inferences
- The most practical "license the AI" route is an app built on the Meta DAT. Glasses stream to the phone and Vantage's model runs on the phone, so Vantage sells the app/SDK to blindness-tech firms such as HumanWare and Envision, or directly to consumers. Inference runs on the phone, not on the glasses.
- Pitch smart-cane and wearable OEMs a hazard-class add-on (stairs, drop-offs, poles, manholes). WeWALK's current obstacle detection is a sensor for upper-body obstacles, not camera-based semantic classes.

### Gaps
- No public revenue-share, royalty or fee terms for Meta DAT, Solos, Vuzix, Brilliant Labs, Xreal or Rokid developer programs. Meta's FAQ page did not mention fees or a commercial distribution timeline.
- No public per-device royalty rates for CV SDKs (Viso.ai is also custom-quote).
- Not established: whether the AITRIOS marketplace lets third parties sell models, and its revenue-share terms.

## 3. Sidewalk / ADA accessibility audits for municipalities

### Takeaway
There is real, recurring municipal demand: ADA transition plans need sidewalk and curb-ramp inventories. But the market is served by vehicle-based mapping vendors such as Cyvl, and observed contracts are small, from thousands to low tens of thousands of dollars. Vantage would likely sell to or partner with these vendors (e.g. supply hazard-class detection) rather than bid against them.

### Cited Findings
- Cyvl markets sidewalk and curb-ramp inventory and condition rating "from the same drive" for ADA transition plans. — [Cyvl Sidewalks & Ramps](https://cyvl.com/solutions/sidewalks-and-ramps/); [Cyvl Sidewalks & ADA](https://cyvl.com/solutions/sidewalks-ada)
- Casa Grande, AZ approved a three-year contract with Cyvl and is described as the first city in Arizona to use AI for this, with an ADA transition plan built from sidewalk and curb-ramp data. The contract value was not on the page. — [Cyvl newsroom](https://cyvl.com/newsroom/pinal-post-casa-grande-first-in-arizona)
- East Wenatchee, WA (June–July 2026) approved Resolution 2026-23: a one-year Cyvl contract "not to exceed $7,500.00" for pavement data collection and management. This is a pavement contract, not sidewalks, but it shows how small these deals are for small cities. — [East Wenatchee agenda packet 06-16-2026](https://www.eastwenatcheewa.gov/AgendaCenter/ViewFile/Agenda/_06162026-449?packet=true); [Item file](https://www.eastwenatcheewa.gov/AgendaCenter/ViewFile/Item/522?fileID=1737)
- PBIC webinar (July 2023): sidewalk inventories cost "$86 – $826 per mile of road" in the six cities that reported data. Methods included manual tablet walking surveys, mobile LiDAR on a Segway or vehicle, crowdsourcing, and GIS/satellite imagery. — [PBIC webinar PDF](https://www.pedbikeinfo.org/pdf/Webinar_PBIC_072623.pdf)
- Repair spending downstream of audits is much larger. Examples: Denver's $3.0M concrete ADA ramp/sidewalk contract (May 2026), Glendale CA's $3.44M ADA curb-ramp/sidewalk contract (2026), and a typical ADA curb ramp at about $5,000 each. — [Denver agenda](https://denver.legistar.com/View.ashx?M=A&ID=1411151&GUID=A6B0CA4C-48C4-47DF-B2B7-4B93908EDAE5); [Glendale agenda](https://glendaleca.primegov.com/Public/CompiledDocument?compileOutputType=1&meetingTemplateId=40711); [East Wenatchee ADA cost appendix](https://www.eastwenatcheewa.gov/AgendaCenter/ViewFile/Item/522?fileID=1737)

### Inferences
- At $86–$826 per mile, a 100-mile small-city inventory is worth roughly $9k–$83k. That is real money, but it needs field collection, GIS deliverables and municipal procurement, which is slow. A phone or dashcam app with Vantage's classes (poles, manholes, utility boxes, bins, bike racks as sidewalk obstructions) could be a cheap data-collection tool licensed to engineering consultancies.

### Gaps
- No verified contract values for Cyvl sidewalk work, Project Sidewalk, DeepWalk, iCyclic, Woolpert, or RoadBotics/Michelin.
- Not researched: UK/EU equivalents, and India's Smart Cities Mission and GeM tenders.

## 4. E-scooter sidewalk-riding detection, delivery robots, and mobility devices

### Takeaway
Scooter sidewalk detection is an established, city-driven niche with funded incumbents: Drover AI and Luna, both partnered with Segway-Ninebot. It is hard for a new entrant to break into. No per-unit prices were found.

### Cited Findings
- Drover AI PathPilot is a front camera plus edge AI that detects sidewalk, street and bike lane in real time and checks parking compliance. Drover raised a $5.4M Series A led by Vektor Partners. — [PR Newswire](https://www.prnewswire.com/news-releases/drover-ai-secures-5-4m-series-a-led-by-vektor-partners-to-scale-its-innovative-applications-of-computer-vision-in-micromobility-301597165.html); [TechCrunch 2022](https://techcrunch.com/2022/07/27/drover-ai-is-using-computer-vision-to-keep-scooter-riders-off-sidewalks/)
- Segway-Ninebot partnered with Drover AI and Luna Systems to integrate sidewalk detection into its AI e-scooters (June 2023). — [TechCrunch 2023](https://techcrunch.com/2023/06/07/segway-partners-with-drover-ai-luna-to-bring-computer-vision-to-e-scooters/)
- Operators used this in city permit bids: Spin promoted Drover's on-vehicle AI in its NYC permit application, and Beam trialled "Pedestrian Shield" powered by PathPilot. — [Smart Cities Dive](https://www.smartcitiesdive.com/news/spin-touts-on-vehicle-ai-platform-in-nyc-permit-application/592411/); [Beam](https://www.ridebeam.com/newsroom/beam-to-launch-trial-of-pedestrian-shield-powered-by-drover-ai-technology-pathpilot)
- SFMTA ran a scooter sidewalk-riding detection technology demonstration. The scooter slows automatically when it detects sidewalk riding. — [SFMTA](https://www.sfmta.com/blog/scooter-sidewalk-riding-detection-technology-demonstration)
- A 2026 operator guide (July 2026) compares Drover PathPilot, Luna ARAS, Segway Pilot, GNSS and IMU approaches, and names "hardware cost" and camera/privacy review as tradeoffs. It gives no prices. — [Levy Fleets guide](https://fleets.levyelectric.com/blog/sidewalk-riding-detection-scooter-fleets)
- Lime explored front-mounted cameras for sidewalk detection. — [Lime engineering blog](https://medium.com/lime-eng/sidewalk-riding-detection-at-lime-baa9291e8697)

### Inferences
- Vantage's crosswalk, curb and sidewalk-object classes overlap with this need. Cheaper on-sensor inference on the IMX500 could be a differentiator for smaller independent fleets, which the Levy guide treats as a buyer segment. Expect a long pilot cycle and privacy review.

### Gaps
- No public per-scooter pricing for Drover or Luna. Superpedestrian's status was not checked in this pass.
- Not researched: WHILL, LUCI, delivery robots, and robot vacuum/lawn makers.

## 5. Facilities / venues / transit wayfinding; data and API sales; elderly care

### Takeaway
Wayfinding vendors (NaviLens, GoodMaps) sell to transit agencies and venues on quote-only pricing, with pilot-first motions. No dollar figures were found in this pass. Dataset/API marketplaces and elderly-care/insurance buyers were not researched within the budget.

### Cited Findings
- NaviLens pricing is by request ("request a demo, pricing and rollout plan") for transit, retail, packaging, tourism, culture, healthcare and education. — [NaviLens contact](https://www.navilens.com/en/contact)
- GoodMaps sells a pilot-first model: "Capture a building with a smartphone using Scan & Go, launch a pilot in weeks." Sound Transit deployed GoodMaps at all 1 Line and 2 Line stations. — [GoodMaps Solutions](https://www.goodmaps.com/solutions); [Sound Transit release](https://www.soundtransit.org/get-to-know-us/news-events/news-releases/sound-transit-adds-goodmaps-wayfinding-tool-riders-to-five); [GoodMaps Sound Transit docs](https://connect.goodmaps.com/docs/soundtransit/)
- St. Louis Metro tested GoodMaps and NaviLens, and Intercity Transit (WA) ran an accessible wayfinding pilot comparing vendors. That presentation notes some solutions "can be costly to implement, with a lengthy timeline." — [Metro St. Louis](https://www.metrostlouis.org/nextstop/testing-accessibility-technology/); [Intercity Transit PDF](https://www.intercitytransit.com/sites/default/files/2024-09/Accessible%20Wayfing%20-%20ITA%20Presentation%20090424.pdf)
- The US ACL Transportation Center lists GoodMaps and NaviLens as promising practices for visually impaired riders. — [ACL](http://acl.gov/TransportationCenter/promising-practices/wayfinding-apps)

### Inferences
- Transit agencies already buy accessibility wayfinding through pilots. Vantage's outdoor hazard detection (stairs, railings, crosswalks) would complement indoor-map vendors like GoodMaps, which makes a partnership or OEM deal more plausible than selling directly to agencies.

### Gaps
- No venue or transit contract dollar values were found for NaviLens, GoodMaps, Aira Access or Lazarillo. Next step: search transit board agendas for "GoodMaps" or "NaviLens" contract amounts.
- Not researched: dataset marketplaces (e.g. Defined.ai, Datarade, Hugging Face paid datasets), inference API pricing, the ROD/COCO license specifics, elderly-care, fall-prevention and insurance buyers, India Smart Cities/GeM, and UK/EU audit equivalents.
