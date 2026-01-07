# NHTSA Signal Naming Convention Reference (Extended)

이 프로젝트는 NHTSA 충돌 데이터베이스의 16자리 채널명 규정을 따릅니다.
데이터셋에 따라 표준 코드(Standard)와 변형 코드(Variant)가 혼용될 수 있음을 유의하십시오.

## 구조 (16 Characters)
- **Char 1-2**: Object (10=Veh1, 00=Barrier)
- **Char 3-6**: General Location
    - 표준: `FORA`(Floor), `ENGN`(Engine)
    - 변형: `FLOR`/`FLPA`(Floor), `VEHC`(Vehicle CG), `LOMA`(Load Matrix)
- **Char 7-10**: Specific Location
    - 표준: `LERE`, `RIFR`
    - 변형: `RE00`(Rear), `CG00`(Center of Gravity)
- **Char 13-14**: Sensor Type
    - 표준: `AC`(Accel), `LC`(Load Cell)
    - 변형: `FO`(Force), `MO`(Moment)
- **Char 15**: Axis (1=X, 2=Y, 3=Z)
- **Char 16**: Rank (P=Primary, R=Redundant)

## 주요 필터링 패턴 (Python 업데이트)
1. **Engine X-axis**: `code.startswith('10ENGN')` OR `code.startswith('10POWT')` ...
2. **Floor Reference (Body)**:
   - `code.startswith('10FORA')` 
   - OR `code.startswith('10FLOR')` 
   - OR `code.startswith('10FLPA')`
3. **Barrier Load**: `code.startswith('00LOMA')` (Force analysis용, 가속도 아님)

## 참조
상세 매핑은 `channel_rules.json`을 참조하십시오.