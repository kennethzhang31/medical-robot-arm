Right Hand Enclosed — 五指／10 個主動自由度
完成日期：2026-10-12；限位更新：2026-10-13

1. 交付內容
mirror_hand_1013.usd：已裝上新版掌面與手背外殼，可直接在 Isaac Sim 開啟。
mirror_hand_1013.urdf 與 meshes/：相同幾何的 URDF，請一起搬移。
Enclosed_Assembly.step：裝上外殼的 CAD 檢視組合，保留在原資料夾。
外殼沿用 SimpleOval 版本，下方兩指保留簡單橢圓開口。
USD 包含網格與材質，不需要旁邊的 STL；URDF 則需要 meshes/。

2. 在 Isaac Sim 使用
開啟 mirror_hand_1013.usd，模型根節點為 /mirror_hand_1013。
模型使用公尺、公斤、秒；USD 角度屬性使用度，URDF 與關節控制 API 通常使用弧度。
保留 Inventor 組合座標及目前 CAD 姿態作為零位；尚未校正實機馬達零點。
手掌固定於世界座標；若要裝到機器手臂，需改接手腕固定關節。
本檔是機構資產，場景、測試物件、重力及接觸材料可由你的測試場景設定。

只控制以下 10 個關節，請依名稱查詢索引，不要假設索引排列：
finger1_abduction_joint / finger1_flexion_joint
finger2_abduction_joint / finger2_flexion_joint
finger3_abduction_joint / finger3_flexion_joint
finger4_abduction_joint / finger4_flexion_joint
finger5_abduction_joint / finger5_flexion_joint
abduction 是指根側擺，flexion 是彎曲；每指兩個主動輸出座標。
請勿對 fingerN_link_joint 或 fingerN_distal_joint 添加控制器或 drive。

3. 為何介面可能顯示超過 10 個關節
URDF 是樹狀模型，含 20 個轉動關節，其中 10 個為被動連桿關節。
USD 再加入 5 個 Link–Distal 閉環鉸鏈，共 25 個 revolute 約束，
其中只有 10 個 drive。Isaac articulation 顯示 20 個座標是正常的，
閉環限制了被動運動，並不代表有 20 個可獨立控制的自由度。
四連桿實測長度為 52、50.5、6、6 mm，使用非線性幾何閉合。
本模型直接驅動指根輸出關節；省略伺服搖臂與球頭拉桿，馬達外形仍保留。
它適合研究手指姿態及建立抓取測試，不是完整雙伺服傳動機構模擬。

4. URDF 姿態預覽
一般 URDF Viewer 不會自動解閉環，單獨拖曳滑桿可能讓連桿分離。
可用 Python 產生一致的連桿角度：
python tools/pose_fourbar.py --flexion-deg 45 --abduction-deg 0
此工具輸出的 jointValues 單位為度；支援每個選項傳入一個值或五個值。
USD 的連桿閉合由物理約束維持，不需要套用線性 mimic。

5. 目前測試參數
依使用者 2026-10-13 提供的機構圖，五指側擺範圍改為 ±20 度，
近端彎曲 0 至 86 度，遠端被動彎曲 0 至 80 度。
以目前 CAD 張開姿態當作零位；圖中 6、13.5 與下方 20 度為安裝角參考，
維持 CAD 實測安裝變換。這些圖示限位與實機馬達零點校正分開處理。
目前四連桿在近端 86 度時，遠端約 71.2405 度；80 度只是遠端限位，
不會強迫遠端轉至 80 度或新增主動自由度。
主動關節 effort 0.25 N·m，速度 1 rad/s。
drive 剛度 0.3 N·m/rad，阻尼 0.01 N·m·s/rad。
所有 CAD 實體暫用密度 1200 kg/m³；總估計質量約 0.3912 kg。
質心與慣量由 CAD 體積積分，但材料、實際質量及控制参数仍需校正。
小螺絲按鄰近主零件分組，主連桿歸屬由 CAD 元件辨識。
碰撞採凸分解，接觸偏移量 0.5 mm；模型自碰撞目前關閉。
這些設定不保證整個活動範圍都不會碰殼；碰撞間隙仍需另外驗證。

6. 已完成的驗證
2026-10-13 新限位已通過 URDF/USD 一致性與 3015 組全範圍幾何閉合檢查。
以下動態與圖片檢查是先前版本的歷史結果，不代表新全行程動態測試通過。
URDF 結構、網格參照、轉軸位置、USD 單位與剛體／慣量檢查通過。
3015 組四連桿姿態的數學閉合檢查通過。
32 張各指端點姿態檢查未見主要零件脫離或明顯錯軸。
Isaac Sim CPU PhysX：120 Hz、240 步、零重力，五指共同彎曲 10 度通過；
運動中最大閉環間隙約 0.00560 mm。交付 USD 未被測試程序改寫。
尚未完成抓取物件接觸、摩擦、負載或實機校正測試。
詳細數值見 Right_Hand_Enclosed.physics_smoke_test.json 及其他 validation 報告。

7. 重新轉換
tools/import_urdf_without_app.py 使用此電腦 C:/isaacsim6.0 的官方匯入器。
修改 URDF 後需依序執行 import_urdf_without_app.py、add_fourbar_closures.py、
validate_usd.py --expected-revolute 25；跨電腦需調整 Isaac 安裝路徑。
本次交付已完成這些步驟，直接使用 USD 即可。
