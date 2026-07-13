-- [지휘관 도메인 - 아군 타격자산 테이블 (무장/탄약별 사거리 + 타격반경 반영)]
-- 기존 strike_asset.sql을 대체하는 버전. 자산 1개당 여러 무장(탄약)을 고를 수 있도록
-- "부대+장비+무장" 조합을 한 행으로 저장한다 (같은 부대·장비라도 무장마다 사거리·타격반경이 다름).
-- MySQL 클라이언트(MySQL Workbench 등)로 직접 실행하세요.
--
-- range_km(사거리) : 발사/투하 지점에서 표적까지 도달 가능한 거리.
-- effect_radius_m(타격반경) : 명중 후 실제 피해를 주는 반경(살상반경/파편반경/자탄 살포반경 등).
--   둘은 서로 다른 개념이며, 공개자료에서 타격반경을 확인하지 못한 무장은 NULL로 두고
--   notes에 근거·한계를 적었다.

CREATE TABLE IF NOT EXISTS `satellite_intel`.`ally_asset` (
    `asset_id`                    INT          NOT NULL AUTO_INCREMENT, -- 고유 번호 (자동 증가)
    `unit_name`                   VARCHAR(50)  NOT NULL,                -- 운용부대명 (예: 제1포병여단)
    `platform_name`               VARCHAR(100) NOT NULL,                -- 장비명 (예: K9A1)
    `category`                    VARCHAR(50)  NOT NULL,                -- 자산 종류 (예: 자주곡사포)
    `munition_name`               VARCHAR(100) NOT NULL,                -- 선택 가능한 무장/탄약 (예: 이중목적고폭탄)
    `range_km`                    DECIMAL(8,2) NOT NULL,                -- 해당 무장 기준 사거리 (km)
    `effect_radius_m`             DECIMAL(8,2),                         -- 명중 시 타격(살상/파편/자탄살포) 반경 (m), 자료 없으면 NULL
    `response_time_min`           INT          NOT NULL,                -- 대응(교전 개시까지) 소요시간 (분)
    `suitable_target_categories`  JSON         NOT NULL,                -- 적합한 표적 대분류 목록
    `notes`                       TEXT,                                 -- 운용/사거리/타격반경 근거 참고사항
    `location_name`               VARCHAR(100),                         -- 배치 위치명
    `latitude`                    DECIMAL(9,6),                         -- 위도 (WGS84, 십진도)
    `longitude`                   DECIMAL(9,6),                         -- 경도 (WGS84, 십진도)
    PRIMARY KEY (`asset_id`),
    UNIQUE KEY `uq_ally_asset_unit_munition` (`unit_name`, `munition_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO `satellite_intel`.`ally_asset`
    (unit_name, platform_name, category, munition_name, range_km, effect_radius_m,
     response_time_min, suitable_target_categories, notes, location_name, latitude, longitude)
VALUES
-- 제11전투비행단 / F-15K (항공전력) -----------------------------------------
(
    '제11전투비행단', 'F-15K', '항공전력', 'KGGB 유도폭탄', 100.00, 100.00, 15,
    JSON_ARRAY('기갑표적', '차량표적', '건설장비', '자주포표적'),
    'GPS/INS 유도 활공폭탄(Mk-82 500lb 기반). 사거리는 투하고도에 따라 약 47~110km(통상 100km). '
    '타격반경은 직접파괴반경 약 30m, 강피해반경 약 100m(effect_radius_m에 대입), '
    '파편위험반경 약 300m(파편 도달 최대 19,200㎡)까지 3단계로 나뉨.',
    '대구 국제공항', 35.900325, 128.638942
),
(
    '제11전투비행단', 'F-15K', '항공전력', '집속탄', 1800.00, 5.00, 15,
    JSON_ARRAY('차량표적', '건설장비'),
    '무유도 투하식 집속탄(자탄 다수 살포)이라 유도무기처럼 스탠드오프 사거리 개념이 없음. '
    '항공기가 목표 상공까지 접근해 투하하므로, 편의상 F-15K 전투행동반경(약 1,800km)을 range_km로 '
    '대입한 추정치. effect_radius_m(5m)은 자탄 1발의 개별 살상반경이며, 실제 전체 살포면적(footprint)은 '
    '공개자료를 찾지 못해 반영하지 못함(추정치, 확인 필요).',
    '대구 국제공항', 35.900325, 128.638942
),
-- 제1포병여단 / K9A1 (자주곡사포) --------------------------------------------
(
    '제1포병여단', 'K9A1', '자주곡사포', '이중목적고폭탄', 36.00, 40.00, 5,
    JSON_ARRAY('차량표적', '건설장비', '기갑표적'),
    'K310 이중목적고폭탄(DPICM) 기준 사거리 36km(최신 사거리연장탄 적용 시 최대 45km 보고). '
    '자탄 49발을 공중에서 방출, 살상면적 약 5,100㎡ -> 원형 환산 반경 약 40m(effect_radius_m). '
    '자탄(K221) 1발 개별 살상반경은 7m 이상, 관통력 100mm 이상.',
    '양주시 남면', 37.896469, 126.979839
),
(
    '제1포병여단', 'K9A1', '자주곡사포', '대전차고폭탄', 3.00, NULL, 5,
    JSON_ARRAY('기갑표적'),
    '대전차고폭탄(HEAT)은 통상 K2 전차 등 전차포 주력탄종이며 K9(곡사포)의 표준 운용탄약은 아님. '
    '성형작약 방식이라 면적형 "반경" 개념보다 "관통력"(점 타격)으로 표기되는 무기라 effect_radius_m은 '
    'NULL로 둠. range_km(3km)도 직사 대전차 교전 기준의 추정 근거리 값(참고용).',
    '양주시 남면', 37.896469, 126.979839
),
-- 제3포병여단 / K-239 천무 (다연장로켓) --------------------------------------
(
    '제3포병여단', 'K-239 천무', '다연장로켓', '130mm 무유도미사일', 36.00, NULL, 10,
    JSON_ARRAY('차량표적', '건설장비'),
    '130mm 로켓(K33 사거리연장탄) 기준 사거리 36km. 탄두 위력·타격반경에 대한 공개자료를 찾지 못해 '
    'effect_radius_m은 NULL로 둠.',
    '인제읍', 38.066614, 128.250756
),
(
    '제3포병여단', 'K-239 천무', '다연장로켓', '600mm 탄도미사일', 290.00, NULL, 10,
    JSON_ARRAY('기갑표적', '자주포표적', '방공표적', '건설장비'),
    '600mm 전술지대지유도탄(KTSSM-II 추정) 기준 사거리 약 290km, CEP 약 9m. 관통형 열압력탄두로 '
    '지하갱도 관통 목적이나, 구체적 타격반경(blast radius)은 비공개라 effect_radius_m은 NULL로 둠.',
    '인제읍', 38.066614, 128.250756
)
ON DUPLICATE KEY UPDATE
    platform_name = VALUES(platform_name),
    category = VALUES(category),
    range_km = VALUES(range_km),
    effect_radius_m = VALUES(effect_radius_m),
    response_time_min = VALUES(response_time_min),
    suitable_target_categories = VALUES(suitable_target_categories),
    notes = VALUES(notes),
    location_name = VALUES(location_name),
    latitude = VALUES(latitude),
    longitude = VALUES(longitude);
