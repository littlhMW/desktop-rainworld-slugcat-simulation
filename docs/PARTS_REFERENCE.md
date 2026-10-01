# 原版部件参考表（机械生成）

由 `tools/parts_audit.py` 调 `tools/parts_table.py` 直接从反编译源码抓取，
**不要手改**；重新生成：`python tools/parts_audit.py`。

读法：`idx` 是 `sLeaser.sprites[]` 下标 = 同容器内的绘制顺序（后画的盖前面的）；
`atlas WxH` 是元件原始像素，实际屏幕尺寸 = 该尺寸 × `DrawSprites` 里赋的 scale。

## 蜥蜴（LizardGraphics）

# 实际屏幕尺寸 = 该尺寸 × DrawSprites 里对应的 scale/scaleX/scaleY。
   idx  下标写法                   元件                         atlas WxH   变换(DrawSprites/Palette)
     i  i                      pixel                      1x1        
            · sLeaser.sprites[i] = fSprite;
            · sLeaser.sprites[i].x = base.owner.bodyChunks[i - DebugBodyChunksStart].pos.x - camPos.x;
            · sLeaser.sprites[i].y = base.owner.bodyChunks[i - DebugBodyChunksStart].pos.y - camPos.y;
            · sLeaser.sprites[i].scale = BodyChunkDisplayRad(i - DebugBodyChunksStart) * lizard.bodyChunks[i - DebugBodyChunksStart].terrainSqueeze * 2f;
            · sLeaser.sprites[i].color = col;
     j  j                      pixel                      1x1        
            · sLeaser.sprites[j] = fSprite2;
            · sLeaser.sprites[j].scale = num6 / 10f;
            · sLeaser.sprites[j].x = vector.x - camPos.x;
            · sLeaser.sprites[j].y = vector.y - camPos.y;
            · sLeaser.sprites[j].color = col;
     k  k                      "LizardArm_0" + val        -          
            · sLeaser.sprites[k] = fSprite3;
            · sLeaser.sprites[k].x = vector3.x - camPos.x;
            · sLeaser.sprites[k].y = vector3.y - camPos.y;
            · sLeaser.sprites[k].rotation = Custom.AimFromOneVectorToAnother(vector4, vector3) - 90f;
            · sLeaser.sprites[k].scaleY = Mathf.Sign(limbs[k - SpriteLimbsStart].flip) * lizard.lizardParams.limbThickness;
            · sLeaser.sprites[k].element = Futile.atlasManager.GetElementWithName("LizardArm_0" + val);
            · sLeaser.sprites[k].element = Futile.atlasManager.GetElementWithName("LizardArm_" + val);
     l  l                      Futile_White               -          
            · sLeaser.sprites[l] = fSprite4;
  num3  num3                   pixel                      1x1        
            · sLeaser.sprites[num3] = fSprite6;
num3 + num2  num3 + num2            pixel                      1x1        
            · sLeaser.sprites[num3 + num2] = fSprite6;
  num4  num4                   Circle20                   20x20      
            · sLeaser.sprites[num4] = fSprite7;
 num10  num10                  pixel                      1x1        
            · sLeaser.sprites[num10] = fSprite8;
k + num8  k + num8               "LizardArmColor_0" + val   -          
            · sLeaser.sprites[k + num8].x = vector3.x - camPos.x;
            · sLeaser.sprites[k + num8].y = vector3.y - camPos.y;
            · sLeaser.sprites[k + num8].rotation = Custom.AimFromOneVectorToAnother(vector4, vector3) - 90f;
            · sLeaser.sprites[k + num8].scaleY = Mathf.Sign(limbs[k - SpriteLimbsStart].flip) * lizard.lizardParams.limbThickness;
            · sLeaser.sprites[k + num8].element = Futile.atlasManager.GetElementWithName("LizardArmColor_0" + val);
            · sLeaser.sprites[k + num8].element = Futile.atlasManager.GetElementWithName("LizardArmColor_" + val);
l + num8  l + num8               ?                          -          
            · sLeaser.sprites[l + num8].alpha = Mathf.Sin(whiteCamoColorAmount * (float)Math.PI) * 0.3f;
            · sLeaser.sprites[l + num8].color = palette.blackColor;
m + num8  m + num8               ?                          -          
            · sLeaser.sprites[m + num8].alpha = Mathf.Lerp(0.3f, 0.1f, Mathf.Abs(Mathf.Lerp(lastDepthRotation, depthRotation, timeStacker)));
            · sLeaser.sprites[m + num8].alpha = 0.3f;
            · sLeaser.sprites[m + num8].color = (blackSalamander ? effectColor : palette.blackColor);
n + num8  n + num8               ?                          -          
            · sLeaser.sprites[n + num8].alpha = Mathf.Lerp(1f, 0.3f, Mathf.Abs(Mathf.Lerp(lastDepthRotation, depthRotation, timeStacker)));
 num13  num13                  ?                          -          
            · sLeaser.sprites[num13].x = vector9.x + normalized3.x * num2 * num * lizard.lizardParams.jawOpenMoveJawsApart * (1f - lizard.lizardParams.jawOpenLowerJ
            · sLeaser.sprites[num13].y = vector9.y + normalized3.y * num2 * num * lizard.lizardParams.jawOpenMoveJawsApart * (1f - lizard.lizardParams.jawOpenLowerJ
            · sLeaser.sprites[num13].rotation = num12 + lizard.lizardParams.jawOpenAngle * (1f - lizard.lizardParams.jawOpenLowerJawFac) * num2 * num;
            · sLeaser.sprites[num13].x = vector9.x - normalized3.x * num2 * num * lizard.lizardParams.jawOpenMoveJawsApart * lizard.lizardParams.jawOpenLowerJawFac 
            · sLeaser.sprites[num13].y = vector9.y - normalized3.y * num2 * num * lizard.lizardParams.jawOpenMoveJawsApart * lizard.lizardParams.jawOpenLowerJawFac 
            · sLeaser.sprites[num13].rotation = num12 - lizard.lizardParams.jawOpenAngle * lizard.lizardParams.jawOpenLowerJawFac * num2 * num;
            · sLeaser.sprites[num13].scaleX = Mathf.Sign(num) * lizard.lizardParams.headSize * iVars.headSize;
            · sLeaser.sprites[num13].scaleY = lizard.lizardParams.headSize * iVars.headSize;
(((0) + 5))  SpriteBodyMesh         triangleMesh2              -          
            · sLeaser.sprites[SpriteBodyMesh] = triangleMesh2;
            · sLeaser.sprites[SpriteBodyMesh].color = col;
((((0) + 5)) + 1)  SpriteTail             triangleMesh2              -          
            · sLeaser.sprites[SpriteTail] = triangleMesh2;
            · sLeaser.sprites[SpriteTail].color = col;
(((((((0) + 5)) + 1) + 1) + limbs.Length)) + num11  SpriteHeadStart + num11 ?                          -          
(((((((0) + 5)) + 1) + 1) + limbs.Length))  SpriteHeadStart        "LizardJaw" + num14 + "." + lizard.lizardParams.headGraphics[0] -          
            · sLeaser.sprites[SpriteHeadStart].element = Futile.atlasManager.GetElementWithName("LizardJaw" + num14 + "." + lizard.lizardParams.headGraphics[0]);
            · sLeaser.sprites[SpriteHeadStart].color = color4;
            · sLeaser.sprites[SpriteHeadStart].color = HeadColor(timeStacker);
            · sLeaser.sprites[SpriteHeadStart].color = palette.blackColor;
(((((((0) + 5)) + 1) + 1) + limbs.Length)) + 1  SpriteHeadStart + 1    "LizardLowerTeeth" + num14 + "." + lizard.lizardParams.headGraphics[1] -          
            · sLeaser.sprites[SpriteHeadStart + 1].element = Futile.atlasManager.GetElementWithName("LizardLowerTeeth" + num14 + "." + lizard.lizardParams.headGraph
            · sLeaser.sprites[SpriteHeadStart + 1].color = HeadColor(timeStacker);
            · sLeaser.sprites[SpriteHeadStart + 1].color = HeadColor(timeStacker);
            · sLeaser.sprites[SpriteHeadStart + 1].color = palette.blackColor;
            · sLeaser.sprites[SpriteHeadStart + 1].color = color;
(((((((0) + 5)) + 1) + 1) + limbs.Length)) + 2  SpriteHeadStart + 2    "LizardUpperTeeth" + num14 + "." + lizard.lizardParams.headGraphics[2] -          
            · sLeaser.sprites[SpriteHeadStart + 2].element = Futile.atlasManager.GetElementWithName("LizardUpperTeeth" + num14 + "." + lizard.lizardParams.headGraph
            · sLeaser.sprites[SpriteHeadStart + 2].color = HeadColor(timeStacker);
            · sLeaser.sprites[SpriteHeadStart + 2].color = palette.blackColor;
            · sLeaser.sprites[SpriteHeadStart + 2].color = Color.Lerp(palette.blackColor, new Color(0.5f, 0.5f, 0.5f), Mathf.Pow(blackLizardLightUpHead, 1f - 0.95f 
            · sLeaser.sprites[SpriteHeadStart + 2].color = palette.blackColor;
            · sLeaser.sprites[SpriteHeadStart + 2].color = color;
(((((((0) + 5)) + 1) + 1) + limbs.Length)) + 3  SpriteHeadStart + 3    "LizardHead" + num14 + "." + overrideHeadGraphic -          
            · sLeaser.sprites[SpriteHeadStart + 3].element = Futile.atlasManager.GetElementWithName("LizardHead" + num14 + "." + overrideHeadGraphic);
            · sLeaser.sprites[SpriteHeadStart + 3].element = Futile.atlasManager.GetElementWithName("LizardHead" + num14 + "." + lizard.lizardParams.headGraphics[3]
            · sLeaser.sprites[SpriteHeadStart + 3].color = color4;
            · sLeaser.sprites[SpriteHeadStart + 3].color = HeadColor(timeStacker);
            · sLeaser.sprites[SpriteHeadStart + 3].color = palette.blackColor;
((((((((0) + 5)) + 1) + 1) + limbs.Length)) + 5) - 1  SpriteHeadEnd - 1      ?                          -          
(((((((0) + 5)) + 1) + 1) + limbs.Length)) + 4  SpriteHeadStart + 4    "LizardEyes" + num14 + "." + lizard.lizardParams.headGraphics[4] -          
            · sLeaser.sprites[SpriteHeadStart + 4].element = Futile.atlasManager.GetElementWithName("LizardEyes" + num14 + "." + lizard.lizardParams.headGraphics[4]
            · sLeaser.sprites[SpriteHeadStart + 4].color = effectColor;
            · sLeaser.sprites[SpriteHeadStart + 4].color = new HSLColor(vector10.x, vector10.y, 0.7f).rgb;
            · sLeaser.sprites[SpriteHeadStart + 4].color = lizard.rotModule.rotColor;
            · sLeaser.sprites[SpriteHeadStart + 4].color = palette.blackColor;
            · sLeaser.sprites[SpriteHeadStart + 4].color = effectColor;
            · sLeaser.sprites[SpriteHeadStart + 4].color = color;
(((((((((((0) + 5)) + 1) + 1) + limbs.Length)) + 5)) + limbs.Length))  SpriteTongueStart      triangleMesh               -          
            · sLeaser.sprites[SpriteTongueStart] = triangleMesh;
            · sLeaser.sprites[SpriteTongueStart].color = palette.blackColor;
(((((((((((0) + 5)) + 1) + 1) + limbs.Length)) + 5)) + limbs.Length)) + 1  SpriteTongueStart + 1  Circle20                   20x20      
            · sLeaser.sprites[SpriteTongueStart + 1] = fSprite5;
            · sLeaser.sprites[SpriteTongueStart + 1].x = vector11.x - camPos.x;
            · sLeaser.sprites[SpriteTongueStart + 1].y = vector11.y - camPos.y;
            · sLeaser.sprites[SpriteTongueStart + 1].rotation = Custom.AimFromOneVectorToAnother(vector11, vector12);
            · sLeaser.sprites[SpriteTongueStart + 1].scaleX = 0.05f * ((lizard.Template.type == CreatureTemplate.Type.BlueLizard) ? 4f : 5f);
            · sLeaser.sprites[SpriteTongueStart + 1].scaleY = 0.05f * Vector2.Distance(vector11, vector12);
            · sLeaser.sprites[SpriteTongueStart + 1].color = effectColor;
            · sLeaser.sprites[SpriteTongueStart + 1].color = palette.blackColor;
((((((((((((((0) + 5)) + 1) + 1) + limbs.Length)) + 5)) + limbs.Length)) + (visualizeVision ? 2 : 0) + ((tongue != null) ? 2 : 0)) + extraSprites)) - 1 - num19  SpriteVisionEnd - 1 - num19 ?                          -          
            · sLeaser.sprites[SpriteVisionEnd - 1 - num19].scaleY = Vector2.Distance(vector9, vector17) * 0.06f;
            · sLeaser.sprites[SpriteVisionEnd - 1 - num19].alpha = Mathf.InverseLerp(0.2f, 1f, eyeBeamsActive);
            · sLeaser.sprites[SpriteVisionEnd - 1 - num19].x = vector17.x - camPos.x;
            · sLeaser.sprites[SpriteVisionEnd - 1 - num19].y = vector17.y - camPos.y;
            · sLeaser.sprites[SpriteVisionEnd - 1 - num19].rotation = Custom.AimFromOneVectorToAnother(vector17, vector9);
((((((((((((((0) + 5)) + 1) + 1) + limbs.Length)) + 5)) + limbs.Length)) + (visualizeVision ? 2 : 0) + ((tongue != null) ? 2 : 0)) + extraSprites)) - 1  SpriteVisionEnd - 1    ?                          -          
((((((((((((((0) + 5)) + 1) + 1) + limbs.Length)) + 5)) + limbs.Length)) + (visualizeVision ? 2 : 0) + ((tongue != null) ? 2 : 0)) + extraSprites)) - 2  SpriteVisionEnd - 2    ?                          -          


## 禅乌贼（CicadaGraphics）

# 实际屏幕尺寸 = 该尺寸 × DrawSprites 里对应的 scale/scaleX/scaleY。
   idx  下标写法                   元件                         atlas WxH   变换(DrawSprites/Palette)
   (0)  BodySprite             "Cicada" + num3 + "body"   0:19x33 1:23x29 2:30x24 3:35x19 4:35x18 5:31x23 6:26x27 7:20x33 8:19x29
            · sLeaser.sprites[BodySprite] = new FSprite("pixel");
            · sLeaser.sprites[BodySprite].scale = iVars.fatness;
            · sLeaser.sprites[BodySprite].element = Futile.atlasManager.GetElementWithName("Cicada" + num3 + "body");
            · sLeaser.sprites[BodySprite].color = color;
     i  i                      ?                          -          
            · sLeaser.sprites[i].x = vector.x - camPos.x + lookDir.x * num5;
            · sLeaser.sprites[i].y = vector.y - camPos.y + lookDir.y * num5;
            · sLeaser.sprites[i].rotation = num6 - num4;
            · sLeaser.sprites[i].scaleX = ((num2 > 0f) ? (-1f) : 1f);
   (1)  HighlightSprite        Circle20                   20x20      
            · sLeaser.sprites[HighlightSprite] = new FSprite("Circle20");
            · sLeaser.sprites[HighlightSprite].scaleX = Mathf.Lerp(5f, 3f, Mathf.Abs(iVars.fatness - 1f) * 10f) / 20f;
            · sLeaser.sprites[HighlightSprite].scaleY = Mathf.Lerp(12f, 8f, Mathf.Abs(iVars.fatness - 1f) * 10f) / 20f;
            · sLeaser.sprites[HighlightSprite].x = Mathf.Lerp(cicada.bodyChunks[1].lastPos.x, cicada.bodyChunks[1].pos.x, timeStacker) - 2f - camPos.x;
            · sLeaser.sprites[HighlightSprite].y = Mathf.Lerp(cicada.bodyChunks[1].lastPos.y, cicada.bodyChunks[1].pos.y, timeStacker) + 3f - camPos.y;
            · sLeaser.sprites[HighlightSprite].rotation = num + 12f;
            · sLeaser.sprites[HighlightSprite].color = Color.Lerp(color, new Color(1f, 1f, 1f), 0.7f);
            · sLeaser.sprites[HighlightSprite].color = Color.Lerp(color, cicada.iVars.color.rgb, 0.07f);
   (6)  HeadSprite             "Cicada" + num3 + "head"   0:23x18 1:22x21 2:22x19 3:17x17 4:16x16 5:19x15 6:21x20 7:22x19 8:23x17
            · sLeaser.sprites[HeadSprite] = new FSprite("pixel");
            · sLeaser.sprites[HeadSprite].element = Futile.atlasManager.GetElementWithName("Cicada" + num3 + "head");
            · sLeaser.sprites[HeadSprite].color = color;
   (7)  ShieldSprite           "Cicada" + num3 + "shield" 0:15x13 1:13x12 2:12x12 3:11x11 4:11x12 5:11x9 6:8x6 7:7x7 8:3x3
            · sLeaser.sprites[ShieldSprite] = new FSprite("pixel");
            · sLeaser.sprites[ShieldSprite].element = Futile.atlasManager.GetElementWithName("Cicada" + num3 + "shield");
            · sLeaser.sprites[ShieldSprite].color = shieldColor;
   (8)  EyesASprite            "Cicada" + num3 + "eyes1"  0:15x7 1:12x8 2:12x7 3:7x7 4:7x7 5:11x7 6:12x7 7:13x7 8:15x7
            · sLeaser.sprites[EyesASprite] = new FSprite("pixel");
            · sLeaser.sprites[EyesASprite].element = Futile.atlasManager.GetElementWithName("Cicada" + num3 + "eyes1");
            · sLeaser.sprites[EyesASprite].color = ((blinkCounter > 0) ? eyeColor : shieldColor);
            · sLeaser.sprites[EyesASprite].color = eyeColor;
            · sLeaser.sprites[EyesASprite].color = eyeColor;
   (9)  EyesBSprite            "Cicada" + num3 + "eyes2"  0:13x5 1:11x6 2:11x5 3:5x5 4:5x5 5:5x5 6:11x5 7:11x5 8:13x5
            · sLeaser.sprites[EyesBSprite] = new FSprite("pixel");
            · sLeaser.sprites[EyesBSprite].element = Futile.atlasManager.GetElementWithName("Cicada" + num3 + "eyes2");
            · sLeaser.sprites[EyesBSprite].color = iVars.color.rgb;
            · sLeaser.sprites[EyesBSprite].color = palette.blackColor;
WingSprite(i, j)  WingSprite(i, j)       CicadaWing" + ((j == 0) ? "A" : "B -          
            · sLeaser.sprites[WingSprite(i, j)] = new FSprite("CicadaWing" + ((j == 0) ? "A" : "B"));
            · sLeaser.sprites[WingSprite(i, j)].scaleY = iVars.wingThickness;
            · sLeaser.sprites[WingSprite(i, j)].color = shieldColor;
TentacleSprite(i, j)  TentacleSprite(i, j)   TriangleMesh([3, pointyTip: true, customColor: false]) -          
            · sLeaser.sprites[TentacleSprite(i, j)] = TriangleMesh.MakeLongMesh(3, pointyTip: true, customColor: false);
            · sLeaser.sprites[TentacleSprite(i, j)].color = color;
WingSprite(k, j)  WingSprite(k, j)       ?                          -          
            · sLeaser.sprites[WingSprite(k, j)].x = p2.x - camPos.x;
            · sLeaser.sprites[WingSprite(k, j)].y = p2.y - camPos.y;
            · sLeaser.sprites[WingSprite(k, j)].alpha = Mathf.Pow(Mathf.Abs(a), 3f);
            · sLeaser.sprites[WingSprite(k, j)].color = Color.Lerp(new Color(0f, 0f, 0f), shieldColor, Mathf.Abs(a) + 0.2f);
            · sLeaser.sprites[WingSprite(k, j)].rotation = num - 180f + (num8 + num10) * ((k == 0) ? (-1f) : 1f);
            · sLeaser.sprites[WingSprite(k, j)].scaleX = Mathf.Pow(Mathf.Max(0f, Mathf.Lerp(Mathf.Abs(p.y), 1f, Mathf.Abs(0.5f - num10) * 1.4f)), 1f) * ((k == 0) ? 
            · sLeaser.sprites[WingSprite(k, j)].scaleX = ((k == 0) ? (-1f) : 1f) * iVars.wingLength;
            · sLeaser.sprites[WingSprite(k, j)].rotation = Custom.AimFromOneVectorToAnother(p2, Vector2.Lerp(wings[k, j].lastPos, wings[k, j].pos, timeStacker)) - 9


## 面条蝇（NeedleWormGraphics）

# 实际屏幕尺寸 = 该尺寸 × DrawSprites 里对应的 scale/scaleX/scaleY。
   idx  下标写法                   元件                         atlas WxH   变换(DrawSprites/Palette)
FangMesh  FangMesh               TriangleMesh([5, pointyTip: true, customColor: true]) -          
            · sLeaser.sprites[FangMesh] = TriangleMesh.MakeLongMesh(5, pointyTip: true, customColor: true);
BodyMesh  BodyMesh               TriangleMesh([TotGraphSegments, pointyTip: true, !small]) -          
            · sLeaser.sprites[BodyMesh] = TriangleMesh.MakeLongMesh(TotGraphSegments, pointyTip: true, !small);
HighLightMesh  HighLightMesh          TriangleMesh([HighLightSegments, pointyTip: true, customColor: true]) -          
            · sLeaser.sprites[HighLightMesh] = TriangleMesh.MakeLongMesh(HighLightSegments, pointyTip: true, customColor: true);
EyeSprite(i)  EyeSprite(i)           JetFishEyeB                4x4        
            · sLeaser.sprites[EyeSprite(i)] = new FSprite("JetFishEyeB");
            · sLeaser.sprites[EyeSprite(i)].x = vector4.x - camPos.x;
            · sLeaser.sprites[EyeSprite(i)].y = vector4.y - camPos.y;
            · sLeaser.sprites[EyeSprite(i)].scaleX = Mathf.Lerp(0.8f, 0.6f, t) * (small ? 0.65f : 1f);
            · sLeaser.sprites[EyeSprite(i)].scaleY = Mathf.Lerp(1.1f, 1.5f, t) * (small ? 0.65f : 1f);
            · sLeaser.sprites[EyeSprite(i)].rotation = Custom.VecToDeg((vector3 + vector).normalized);
     i  i                      ?                          -          
            · sLeaser.sprites[i].color = bodyColor;
EyeSprite(j)  EyeSprite(j)           ?                          -          
            · sLeaser.sprites[EyeSprite(j)].color = eyeColor;
WingSprite(i, j)  WingSprite(i, j)       new CustomFSprite("CentipedeWing") -          
            · sLeaser.sprites[WingSprite(i, j)] = new CustomFSprite("CentipedeWing");
LumpSprite(i, j)  LumpSprite(i, j)       JetFishEyeB                4x4        
            · sLeaser.sprites[LumpSprite(i, j)] = new FSprite("JetFishEyeB");
LegSprite(k, l)  LegSprite(k, l)        new CustomFSprite("JetFishFlipper3") -          
            · sLeaser.sprites[LegSprite(k, l)] = new CustomFSprite("JetFishFlipper3");
WingSprite(num8, m)  WingSprite(num8, m)    ?                          -          
LumpSprite(num8, m)  LumpSprite(num8, m)    ?                          -          
            · sLeaser.sprites[LumpSprite(num8, m)].x = vector14.x - camPos.x;
            · sLeaser.sprites[LumpSprite(num8, m)].y = vector14.y - camPos.y;
            · sLeaser.sprites[LumpSprite(num8, m)].scaleX = 0.9f;
            · sLeaser.sprites[LumpSprite(num8, m)].scaleY = 1.2f;
            · sLeaser.sprites[LumpSprite(num8, m)].rotation = Custom.VecToDeg(segmentDir);
            · sLeaser.sprites[LumpSprite(num8, m)].color = ((num8 == 0) ? bodyColor : Color.Lerp(bodyColor, highLightColor, Mathf.Abs(vector2.x) * 0.6f));


## 拾荒者（ScavengerGraphics）

# 实际屏幕尺寸 = 该尺寸 × DrawSprites 里对应的 scale/scaleX/scaleY。
   idx  下标写法                   元件                         atlas WxH   变换(DrawSprites/Palette)
firstSprite  firstSprite            new TriangleMesh("Futile_White", tris, customColor: true) -          
            · sLeaser.sprites[firstSprite] = new TriangleMesh("Futile_White", tris, customColor: true);
            · sLeaser.sprites[firstSprite] = new TriangleMesh("Futile_White", tris, customColor: true);
   num  num                    TriangleMesh([points[i].Length, pointyTip: false, owner.iVars.coloredEartlerTips]) -          
            · sLeaser.sprites[num] = TriangleMesh.MakeLongMesh(points[i].Length, pointyTip: false, owner.iVars.coloredEartlerTips);
firstSprite + i  firstSprite + i        ?                          -          
            · sLeaser.sprites[firstSprite + i].color = headColor;
 (get)  ChestPatchSprite/ChestSprite/HeadSprite/HipSprite/MarkSprite/NeckSprite/TeethSprite/WaistSprite TriangleMesh([4, pointyTip: false, customColor: true]) -          
            · sLeaser.sprites[ChestSprite] = new FSprite("Circle20");
            · sLeaser.sprites[ChestSprite].scaleX = base.owner.bodyChunks[0].rad * Mathf.Lerp(0.7f, 1.3f, iVars.fatness) / 10f;
            · sLeaser.sprites[ChestSprite].scaleY = (base.owner.bodyChunks[0].rad + Mathf.Lerp(2f, 1.5f, iVars.narrowWaist)) / 10f;
            · sLeaser.sprites[HipSprite] = new FSprite("Circle20");
            · sLeaser.sprites[HipSprite].scale = base.owner.bodyChunks[1].rad / 15f;
            · sLeaser.sprites[HeadSprite] = new FSprite("Circle20");
            · sLeaser.sprites[WaistSprite] = new TriangleMesh("Futile_White", array, customColor: false);
            · sLeaser.sprites[NeckSprite] = TriangleMesh.MakeLongMesh(4, pointyTip: false, customColor: true);
            · sLeaser.sprites[TeethSprite] = new TriangleMesh("Futile_White", array, customColor: false);
            · sLeaser.sprites[ChestPatchSprite] = new TriangleMesh("Futile_White", array, customColor: false);
            · sLeaser.sprites[MarkSprite] = new FSprite("pixel");
            · sLeaser.sprites[MarkSprite].scale = 5f;
            · sLeaser.sprites[ChestSprite].x = float3.x - @float.x;
            · sLeaser.sprites[ChestSprite].y = float3.y - @float.y;
            · sLeaser.sprites[ChestSprite].rotation = Custom.AimFromOneVectorToAnother(float3, float5);
            · sLeaser.sprites[HipSprite].x = float4.x - @float.x;
            · sLeaser.sprites[HipSprite].y = float4.y - @float.y;
            · sLeaser.sprites[HeadSprite].x = float2.x - @float.x;
            · sLeaser.sprites[HeadSprite].y = float2.y - @float.y;
            · sLeaser.sprites[MarkSprite].x = float2.x - @float.x;
            · sLeaser.sprites[MarkSprite].y = float2.y - @float.y + 32f;
            · sLeaser.sprites[MarkSprite].alpha = Mathf.Lerp(lastMarkAlpha, markAlpha, timeStacker);
            · sLeaser.sprites[HeadSprite].rotation = Custom.VecToDeg(f2.normalized());
            · sLeaser.sprites[HeadSprite].scaleX = Mathf.Lerp(8f, 9f, Mathf.Pow(num9, 0.5f)) * num11 / 10f;
            · sLeaser.sprites[HeadSprite].scaleY = Mathf.Lerp(11f, 8f, Mathf.Pow(num9, 0.5f)) * num11 / 10f;
            · sLeaser.sprites[ChestSprite].color = blendedBodyColor;
            · sLeaser.sprites[HipSprite].color = blendedBodyColor;
            · sLeaser.sprites[WaistSprite].color = blendedBodyColor;
            · sLeaser.sprites[NeckSprite].color = blendedBodyColor;
            · sLeaser.sprites[HeadSprite].color = blendedHeadColor;
            · sLeaser.sprites[TeethSprite].color = blendedHeadColor;
            · sLeaser.sprites[ChestPatchSprite].color = Color.Lerp(bellyColor.rgb, palette.blackColor, Mathf.Lerp(bellyColorBlack, 1f, darkness));
(get) + j  FirstBehindLimbSprite + j/FirstInFrontLimbSprite + j ?                          -          
            · sLeaser.sprites[FirstBehindLimbSprite + j].color = blendedBodyColor;
            · sLeaser.sprites[FirstInFrontLimbSprite + j].color = blendedBodyColor;
firstSprite + 1  firstSprite + 1        flag ? "ScavengerHandB" : "ScavengerHandA" -          
            · sLeaser.sprites[firstSprite + 1] = new FSprite("pixel");
            · sLeaser.sprites[firstSprite + 1].x = float3.x - camPos.x;
            · sLeaser.sprites[firstSprite + 1].y = float3.y - camPos.y;
            · sLeaser.sprites[firstSprite + 1].element = Futile.atlasManager.GetElementWithName(flag ? "ScavengerHandB" : "ScavengerHandA");
            · sLeaser.sprites[firstSprite + 1].rotation = Custom.AimFromOneVectorToAnother(float3, float2);
            · sLeaser.sprites[firstSprite + 1].scaleX = (0f - num * 2f) * 3f / 18f;
            · sLeaser.sprites[firstSprite + 1] = new FSprite("pixel");
(get) + 1  MarkSprite + 1         Futile_White               -          
            · sLeaser.sprites[MarkSprite + 1] = new FSprite("Futile_White");
            · sLeaser.sprites[MarkSprite + 1].x = float2.x - @float.x;
            · sLeaser.sprites[MarkSprite + 1].y = float2.y - @float.y + 32f;
            · sLeaser.sprites[MarkSprite + 1].alpha = 0.2f * Mathf.Lerp(lastMarkAlpha, markAlpha, timeStacker);
            · sLeaser.sprites[MarkSprite + 1].scale = 1f + Mathf.Lerp(lastMarkAlpha, markAlpha, timeStacker);
firstSprite + 2  firstSprite + 2        pixel                      1x1        
            · sLeaser.sprites[firstSprite + 2] = new FSprite("pixel");
EyeSprite(i, j)  EyeSprite(i, j)        Circle20                   20x20      
            · sLeaser.sprites[EyeSprite(i, j)] = new FSprite("Circle20");
EyeSprite(j, 0)  EyeSprite(j, 0)        ?                          -          
            · sLeaser.sprites[EyeSprite(j, 0)].x = float16.x - @float.x;
            · sLeaser.sprites[EyeSprite(j, 0)].y = float16.y - @float.y;
            · sLeaser.sprites[EyeSprite(j, 0)].scaleX = num16 * 0.1f;
            · sLeaser.sprites[EyeSprite(j, 0)].scaleY = num17 * 0.1f;
            · sLeaser.sprites[EyeSprite(j, 0)].rotation = num15;
EyeSprite(j, 1)  EyeSprite(j, 1)        ?                          -          
            · sLeaser.sprites[EyeSprite(j, 1)].x = float16.x + vec.x - @float.x;
            · sLeaser.sprites[EyeSprite(j, 1)].y = float16.y + vec.y - @float.y;
            · sLeaser.sprites[EyeSprite(j, 1)].scaleX = num16 * 0.1f * iVars.pupilSize * (1f - 0.5f * num13);
            · sLeaser.sprites[EyeSprite(j, 1)].scaleY = num17 * 0.1f * iVars.pupilSize * (1f - 0.5f * num13);
            · sLeaser.sprites[EyeSprite(j, 1)].rotation = num15;
EyeSprite(k, l)  EyeSprite(k, l)        ?                          -          
            · sLeaser.sprites[EyeSprite(k, l)].color = new Color(0.3f, 0.3f, 0.3f);
EyeSprite(num, 0)  EyeSprite(num, 0)      ?                          -          
            · sLeaser.sprites[EyeSprite(num, 0)].color = BlendedEyeColor;
            · sLeaser.sprites[EyeSprite(num, 0)].color = Color.Lerp(BlendedEyeColor, new Color(1f, 1f, 1f), 0.5f);
            · sLeaser.sprites[EyeSprite(num, 0)].color = Color.Lerp(BlendedEyeColor, Color.Lerp(blendedBodyColor, blendedHeadColor, 0.5f), 0.5f);
EyeSprite(num, 1)  EyeSprite(num, 1)      ?                          -          
            · sLeaser.sprites[EyeSprite(num, 1)].color = Color.Lerp(BlendedEyeColor, Color.Lerp(blendedBodyColor, blendedHeadColor, 0.5f), 0.5f);
            · sLeaser.sprites[EyeSprite(num, 1)].color = Color.Lerp(BlendedEyeColor, new Color(1f, 1f, 1f), 0.5f);
            · sLeaser.sprites[EyeSprite(num, 1)].color = Custom.HSL2RGB(bodyColor.hue, 1f, 0.35f);
            · sLeaser.sprites[EyeSprite(num, 1)].color = Custom.HSL2RGB(headColor.hue, 1f, 0.35f);
            · sLeaser.sprites[EyeSprite(num, 1)].color = Custom.HSL2RGB(decorationColor.hue, 1f, 0.35f);
            · sLeaser.sprites[EyeSprite(num, 1)].color = Color.Lerp(Custom.HSL2RGB(headColor.hue, headColor.saturation, 0.15f), blackColor, headColorBlack);
            · sLeaser.sprites[EyeSprite(num, 1)].color = blendedHeadColor;


## 蝠蝇（FlyGraphics）

# 实际屏幕尺寸 = 该尺寸 × DrawSprites 里对应的 scale/scaleX/scaleY。
   idx  下标写法                   元件                         atlas WxH   变换(DrawSprites/Palette)
     0  0                      FlyBody                    5x12       
            · sLeaser.sprites[0] = new FSprite("FlyBody");
            · sLeaser.sprites[0].color = new Color(0f, 0f, 1f);
            · sLeaser.sprites[0].x = vector.x;
            · sLeaser.sprites[0].y = vector.y;
            · sLeaser.sprites[0].rotation = num;
     i  i                      ?                          -          
            · sLeaser.sprites[i].color = palette.blackColor;
     1  1                      FlyWing                    9x15       
            · sLeaser.sprites[1] = new FSprite("FlyWing");
            · sLeaser.sprites[1].x = vector.x;
            · sLeaser.sprites[1].y = vector.y;
 1 + i  1 + i                  ?                          -          
            · sLeaser.sprites[1 + i].rotation = ((i == 0) ? (-1f) : 1f) * (40f + 150f * a) + num;
            · sLeaser.sprites[1 + i].scaleX = ((i == 0) ? (-1f) : 1f) * ((fly.flapSpeed < 0f) ? 1f : (1f - 0.6f * (Mathf.Sin(Mathf.Lerp(wings[i, 1], wings[i, 0], ti
     2  2                      FlyWing                    9x15       
            · sLeaser.sprites[2] = new FSprite("FlyWing");
            · sLeaser.sprites[2].x = vector.x;
            · sLeaser.sprites[2].y = vector.y;
     3  3                      FlyEyes                    5x3        
            · sLeaser.sprites[3] = new FSprite("FlyEyes");
            · sLeaser.sprites[3].x = vector.x;
            · sLeaser.sprites[3].y = vector.y;
            · sLeaser.sprites[3].rotation = num;


## 爆米花（SeedCob）

# 实际屏幕尺寸 = 该尺寸 × DrawSprites 里对应的 scale/scaleX/scaleY。
   idx  下标写法                   元件                         atlas WxH   变换(DrawSprites/Palette)
   (0)  StalkSprite(0)         TriangleMesh([stalkSegments, pointyTip: false, customColor: false]) -          
            · sLeaser.sprites[StalkSprite(0)] = TriangleMesh.MakeLongMesh(stalkSegments, pointyTip: false, customColor: false);
            · sLeaser.sprites[StalkSprite(0)].color = palette.blackColor;
            · sLeaser.sprites[StalkSprite(0)].color = color;
ShellSprite(i)  ShellSprite(i)         TriangleMesh([cobSegments, pointyTip: false, customColor: true]) -          
            · sLeaser.sprites[ShellSprite(i)] = TriangleMesh.MakeLongMesh(cobSegments, pointyTip: false, customColor: true);
LeafSprite(k)  LeafSprite(k)          CentipedeLegB              4x26       
            · sLeaser.sprites[LeafSprite(k)] = new FSprite("CentipedeLegB");
            · sLeaser.sprites[LeafSprite(k)].scaleX = leaves[k, 3].x;
LeafSprite(num14)  LeafSprite(num14)      ?                          -          
            · sLeaser.sprites[LeafSprite(num14)].x = vector2.x - camPos.x;
            · sLeaser.sprites[LeafSprite(num14)].y = vector2.y - camPos.y;
            · sLeaser.sprites[LeafSprite(num14)].rotation = Custom.AimFromOneVectorToAnother(vector2, vector19);
            · sLeaser.sprites[LeafSprite(num14)].scaleY = Vector2.Distance(vector2, vector19) / 26f;
LeafSprite(m)  LeafSprite(m)          ?                          -          
            · sLeaser.sprites[LeafSprite(m)].color = palette.blackColor;
            · sLeaser.sprites[LeafSprite(m)].color = color;
   (1)  StalkSprite(1)         TriangleMesh([stalkSegments, pointyTip: false, customColor: true]) -          
            · sLeaser.sprites[StalkSprite(1)] = TriangleMesh.MakeLongMesh(stalkSegments, pointyTip: false, customColor: true);
   (2)  CobSprite              TriangleMesh([cobSegments, pointyTip: false, customColor: false]) -          
            · sLeaser.sprites[CobSprite] = TriangleMesh.MakeLongMesh(cobSegments, pointyTip: false, customColor: false);
            · sLeaser.sprites[CobSprite].color = yellowColor;
            · sLeaser.sprites[CobSprite].color = yellowColor;
SeedSprite(j, 0)  SeedSprite(j, 0)       JetFishEyeA                6x6        
            · sLeaser.sprites[SeedSprite(j, 0)] = new FSprite("JetFishEyeA");
SeedSprite(j, 1)  SeedSprite(j, 1)       JetFishEyeA                6x6        
            · sLeaser.sprites[SeedSprite(j, 1)] = new FSprite("JetFishEyeA");
SeedSprite(j, 2)  SeedSprite(j, 2)       pixel                      1x1        
            · sLeaser.sprites[SeedSprite(j, 2)] = new FSprite("pixel");
SeedSprite(n, 0)  SeedSprite(n, 0)       ?                          -          
            · sLeaser.sprites[SeedSprite(n, 0)].scale = (seedsPopped[n] ? num13 : 0.35f);
            · sLeaser.sprites[SeedSprite(n, 0)].x = vector17.x - camPos.x;
            · sLeaser.sprites[SeedSprite(n, 0)].y = vector17.y - camPos.y;
SeedSprite(n, 1)  SeedSprite(n, 1)       ?                          -          
            · sLeaser.sprites[SeedSprite(n, 1)].x = vector17.x + vector18.x * 0.35f - camPos.x;
            · sLeaser.sprites[SeedSprite(n, 1)].y = vector17.y + vector18.y * 0.35f - camPos.y;
            · sLeaser.sprites[SeedSprite(n, 1)].scale = (seedsPopped[n] ? num13 : 0.4f) * 0.5f;
SeedSprite(n, 2)  SeedSprite(n, 2)       "tinyStar"                 -          
            · sLeaser.sprites[SeedSprite(n, 2)].element = Futile.atlasManager.GetElementWithName("tinyStar");
            · sLeaser.sprites[SeedSprite(n, 2)].rotation = Custom.VecToDeg(vector15);
            · sLeaser.sprites[SeedSprite(n, 2)].scaleX = Mathf.Pow(1f - Mathf.Abs(seedPositions[n].x), 0.2f);
            · sLeaser.sprites[SeedSprite(n, 2)].x = vector17.x + vector18.x - camPos.x;
            · sLeaser.sprites[SeedSprite(n, 2)].y = vector17.y + vector18.y - camPos.y;
SeedSprite(l, 0)  SeedSprite(l, 0)       ?                          -          
            · sLeaser.sprites[SeedSprite(l, 0)].color = yellowColor;
            · sLeaser.sprites[SeedSprite(l, 0)].color = Color.Lerp(sLeaser.sprites[SeedSprite(l, 0)].color, palette.blackColor, 0.7f);
            · sLeaser.sprites[SeedSprite(l, 0)].color = yellowColor;
            · sLeaser.sprites[SeedSprite(l, 0)].color = Color.Lerp(sLeaser.sprites[SeedSprite(l, 0)].color, color, 0.7f);
SeedSprite(l, 1)  SeedSprite(l, 1)       ?                          -          
            · sLeaser.sprites[SeedSprite(l, 1)].color = color2;
            · sLeaser.sprites[SeedSprite(l, 1)].color = Color.Lerp(sLeaser.sprites[SeedSprite(l, 1)].color, palette.blackColor, 0.5f);
            · sLeaser.sprites[SeedSprite(l, 1)].color = color2;
            · sLeaser.sprites[SeedSprite(l, 1)].color = Color.Lerp(sLeaser.sprites[SeedSprite(l, 1)].color, color, 0.5f);
SeedSprite(l, 2)  SeedSprite(l, 2)       ?                          -          
            · sLeaser.sprites[SeedSprite(l, 2)].color = Color.Lerp(color, palette.blackColor, AbstractCob.dead ? 0.6f : 0.3f);
            · sLeaser.sprites[SeedSprite(l, 2)].color = Color.Lerp(sLeaser.sprites[SeedSprite(l, 2)].color, palette.blackColor, 0.9f);
            · sLeaser.sprites[SeedSprite(l, 2)].color = Color.Lerp(a2, color, (!AbstractCob.dead) ? 0.3f : 0.6f);
            · sLeaser.sprites[SeedSprite(l, 2)].color = Color.Lerp(sLeaser.sprites[SeedSprite(l, 2)].color, color, 0.9f);


## 矛（Spear）

# 实际屏幕尺寸 = 该尺寸 × DrawSprites 里对应的 scale/scaleX/scaleY。
   idx  下标写法                   元件                         atlas WxH   变换(DrawSprites/Palette)
     0  0                      "BioSpear" + (spearmasterNeedleType % 3 + 1) -          
            · sLeaser.sprites[0] = TriangleMesh.MakeLongMesh(points.GetLength(0), pointyTip: false, customColor: true);
            · sLeaser.sprites[0] = new FSprite("BioSpear" + (spearmasterNeedleType % 3 + 1));
            · sLeaser.sprites[0] = new FSprite("FireBugSpearColor");
            · sLeaser.sprites[0] = TriangleMesh.MakeLongMesh(1, pointyTip: false, customColor: true);
            · sLeaser.sprites[0] = new FSprite("SmallSpear");
            · sLeaser.sprites[0].x = vector4.x - camPos.x;
            · sLeaser.sprites[0].y = vector4.y - camPos.y;
            · sLeaser.sprites[0].rotation = Custom.VecToDeg(vector3);
            · sLeaser.sprites[0].color = base.blinkColor;
            · sLeaser.sprites[0].color = jollyCustomColor.Value;
            · sLeaser.sprites[0].color = Color.Lerp(PlayerGraphics.CustomColorSafety(2), color, 1f - num4);
            · sLeaser.sprites[0].color = Color.Lerp(new Color(1f, 1f, 1f, 1f), color, 1f - num4);
            · sLeaser.sprites[0].element = Futile.atlasManager.GetElementWithName("BioSpear" + (spearmasterNeedleType % 3 + 1));
            · sLeaser.sprites[0].color = color;
            · sLeaser.sprites[0].color = Custom.HSL2RGB(Custom.Decimal(abstractSpear.hue + EggBugGraphics.HUE_OFF), 1f, 0.5f);
            · sLeaser.sprites[0].color = color;
   num  num                    ?                          -          
            · sLeaser.sprites[num].x = vector.x - camPos.x;
            · sLeaser.sprites[num].y = vector.y - camPos.y;
            · sLeaser.sprites[num].rotation = Custom.AimFromOneVectorToAnother(new Vector2(0f, 0f), vector2);
     1  1                      FireBugSpear               6x51       
            · sLeaser.sprites[1] = new FSprite("FireBugSpear");
            · sLeaser.sprites[1] = new FSprite("SmallSpear");
            · sLeaser.sprites[1].color = base.blinkColor;
            · sLeaser.sprites[1].color = color;
            · sLeaser.sprites[1].color = base.blinkColor;
            · sLeaser.sprites[1].color = color;
            · sLeaser.sprites[1].color = color;


## 珍珠（DataPearl）

# 实际屏幕尺寸 = 该尺寸 × DrawSprites 里对应的 scale/scaleX/scaleY。
   idx  下标写法                   元件                         atlas WxH   变换(DrawSprites/Palette)
     0  0                      Pebble" + UnityEngine.Random.Range(5, 8 -          
            · sLeaser.sprites[0] = new FSprite("Pebble" + UnityEngine.Random.Range(5, 8));
            · sLeaser.sprites[0].scaleX = Mathf.Lerp(0.5f, 1.5f, value) * 1.2f;
            · sLeaser.sprites[0].scaleY = Mathf.Lerp(0.5f, 1.5f, 1f - value) * 1.2f;
            · sLeaser.sprites[0].rotation = UnityEngine.Random.value * 360f;
            · sLeaser.sprites[0].x = vector.x - camPos.x;
            · sLeaser.sprites[0].y = vector.y - camPos.y - spriteDown;
            · sLeaser.sprites[0].color = Color.Lerp(palette.blackColor, palette.fogColor, palette.fogAmount * 0.1f);
            · sLeaser.sprites[0] = new FSprite("JetFishEyeA");
            · sLeaser.sprites[0].x = vector.x - camPos.x;
            · sLeaser.sprites[0].y = vector.y - camPos.y;
            · sLeaser.sprites[0].color = Color.Lerp(Custom.RGB2RGBA(color * Mathf.Lerp(1f, 0.2f, darkness), 1f), new Color(1f, 1f, 1f), num);
            · sLeaser.sprites[0].color = new Color(0f, 0.003921569f, 0f);
     1  1                      tinyStar                   3x3        
            · sLeaser.sprites[1] = new FSprite("tinyStar");
            · sLeaser.sprites[1].x = vector.x - camPos.x - 0.5f;
            · sLeaser.sprites[1].y = vector.y - camPos.y + 1.5f;
            · sLeaser.sprites[1].color = Color.Lerp(Custom.RGB2RGBA(highlightColor.Value * Mathf.Lerp(1f, 0.5f, darkness), 1f), b, num);
            · sLeaser.sprites[1].color = Color.Lerp(Custom.RGB2RGBA(color * Mathf.Lerp(1.3f, 0.5f, darkness), 1f), new Color(1f, 1f, 1f), Mathf.Lerp(0.5f + 0.5f * n
            · sLeaser.sprites[1].color = new Color(0f, 0.003921569f, 0f);
     2  2                      Futile_White               -          
            · sLeaser.sprites[2] = new FSprite("Futile_White");
            · sLeaser.sprites[2].x = vector.x - camPos.x;
            · sLeaser.sprites[2].y = vector.y - camPos.y;
            · sLeaser.sprites[2].color = b;
            · sLeaser.sprites[2].alpha = num * 0.5f;
            · sLeaser.sprites[2].scale = 20f * num * ((AbstractPearl.dataPearlType != AbstractDataPearl.DataPearlType.Misc && AbstractPearl.dataPearlType != Abstrac


## 蛞蝓猫(手/尾)（PlayerGraphics）

# 实际屏幕尺寸 = 该尺寸 × DrawSprites 里对应的 scale/scaleX/scaleY。
   idx  下标写法                   元件                         atlas WxH   变换(DrawSprites/Palette)
   num  num                    LizardScaleA" + graphic    -          
            · sLeaser.sprites[num] = new FSprite("LizardScaleA" + graphic);
            · sLeaser.sprites[num].scaleY = scaleObjects[num - startSprite].length / graphicHeight;
            · sLeaser.sprites[num].x = p.x - camPos.x;
            · sLeaser.sprites[num].y = p.y - camPos.y;
            · sLeaser.sprites[num].rotation = Custom.AimFromOneVectorToAnother(p, Vector2.Lerp(scaleObjects[num - startSprite].lastPos, scaleObjects[num - startSpri
            · sLeaser.sprites[num].scaleX = scaleObjects[num - startSprite].width * Mathf.Sign(f);
            · sLeaser.sprites[num].color = baseColor;
  num3  num3                   ?                          -          
            · sLeaser.sprites[num3].color = baseColor;
startSprite  startSprite            TriangleMesh([segments.GetLength(0]) -          
            · sLeaser.sprites[startSprite] = TriangleMesh.MakeLongMesh(segments.GetLength(0), pointyTip: false, customColor: true);
            · sLeaser.sprites[startSprite] = new FSprite("JetFishEyeA");
            · sLeaser.sprites[startSprite].x = vector.x - camPos.x;
            · sLeaser.sprites[startSprite].y = vector.y - camPos.y;
            · sLeaser.sprites[startSprite].rotation = rotation;
            · sLeaser.sprites[startSprite].scaleX = 1f;
            · sLeaser.sprites[startSprite].scaleX = 0.5f;
            · sLeaser.sprites[startSprite].scaleX = Custom.LerpMap(Mathf.Abs(pGraphics.player.mainBodyChunk.vel.x), 0f, 4f, 1f, 0.75f);
            · sLeaser.sprites[startSprite].color = Color.Lerp(Custom.RGB2RGBA(this.color * Mathf.Lerp(1f, 0.2f, darkness), 1f), new Color(1f, 1f, 1f), num);
            · sLeaser.sprites[startSprite].color = new Color(0f, 0.003921569f, 0f);
            · sLeaser.sprites[startSprite].alpha = globalAlpha;
startSprite + i * lines + j  startSprite + i * lines + j tinyStar                   3x3        
            · sLeaser.sprites[startSprite + i * lines + j].x = vector.x - camPos.x;
            · sLeaser.sprites[startSprite + i * lines + j].y = vector.y - camPos.y;
            · sLeaser.sprites[startSprite + i * lines + j].color = new Color(1f, 0f, 0f);
            · sLeaser.sprites[startSprite + i * lines + j].rotation = Custom.VecToDeg(playerSpineData.dir);
            · sLeaser.sprites[startSprite + i * lines + j].scaleX = Custom.LerpMap(Mathf.Abs(num3), 0.4f, 1f, 1f, 0f);
            · sLeaser.sprites[startSprite + i * lines + j].scaleY = 1f;
            · sLeaser.sprites[startSprite + i * lines + j].color = JollyColor(pGraphics.player.playerState.playerNumber, 2);
            · sLeaser.sprites[startSprite + i * lines + j].color = CustomColorSafety(2);
            · sLeaser.sprites[startSprite + i * lines + j].color = Color.gray;
            · sLeaser.sprites[startSprite + i * lines + j].color = color2;
            · sLeaser.sprites[startSprite + i * lines + j] = new FSprite("tinyStar");
            · sLeaser.sprites[startSprite + i * lines + j].x = a.x - camPos.x;
            · sLeaser.sprites[startSprite + i * lines + j].y = a.y - camPos.y;
            · sLeaser.sprites[startSprite + i * lines + j].rotation = Custom.VecToDeg(Vector2.Lerp(playerSpineData.dir, b, num2)) - Mathf.Lerp(0f, 30f, 1f - num4) *
            · sLeaser.sprites[startSprite + i * lines + j].scaleX = Mathf.Lerp(num6, 1f, 0.25f) * ((num5 > 0f) ? 1f : (-1f)) * 0.8f;
            · sLeaser.sprites[startSprite + i * lines + j].scaleY = num6;
            · sLeaser.sprites[startSprite + i * lines + j] = new VertexColorSprite((num > 0f) ? "WeaverFeather1" : "WeaverFeather2", quadType: false) { anchorY = 0.
startSprite + lines * rows  startSprite + lines * rows "BioSpear" + (spearType % 3 + 1) -          
            · sLeaser.sprites[startSprite + lines * rows].x = vector.x - camPos.x;
            · sLeaser.sprites[startSprite + lines * rows].y = vector.y - camPos.y;
            · sLeaser.sprites[startSprite + lines * rows].color = JollyColor(pGraphics.player.playerState.playerNumber, 2);
            · sLeaser.sprites[startSprite + lines * rows].color = CustomColorSafety(2);
            · sLeaser.sprites[startSprite + lines * rows].color = Color.white;
            · sLeaser.sprites[startSprite + lines * rows].rotation = rotation;
            · sLeaser.sprites[startSprite + lines * rows].scaleY = (0f - spearProg) * 0.5f;
            · sLeaser.sprites[startSprite + lines * rows].element = Futile.atlasManager.GetElementWithName("BioSpear" + (spearType % 3 + 1));
startSprite + rows * lines  startSprite + rows * lines BioSpear" + (spearType % 3 + 1 -          
            · sLeaser.sprites[startSprite + rows * lines] = new FSprite("BioSpear" + (spearType % 3 + 1));
sprite  sprite                 TriangleMesh.MakeGridMesh("MoonCloakTex", divs - 1) -          
            · sLeaser.sprites[sprite] = TriangleMesh.MakeGridMesh("MoonCloakTex", divs - 1);
haloFirstSprite  haloFirstSprite        new TriangleMesh("Futile_White", array, customColor: false)
			{
				shader = rCam.game.rainWorld.Shaders[inEndingRoom ? "WeaverGlowNoGrab" : "WeaverGlow"]
			} -          
            · sLeaser.sprites[haloFirstSprite].alpha = num13;
            · sLeaser.sprites[haloFirstSprite] = new TriangleMesh("Futile_White", array, customColor: false) { shader = rCam.game.rainWorld.Shaders[inEndingRoom ? "
            · sLeaser.sprites[haloFirstSprite].color = color;
            · sLeaser.sprites[haloFirstSprite].alpha = 0f;
     0  0                      BodyA                      14x19      
            · sLeaser.sprites[0] = new FSprite("BodyA");
            · sLeaser.sprites[0].scaleY = 0.5f;
            · sLeaser.sprites[0].x = vector.x - camPos.x;
            · sLeaser.sprites[0].y = vector.y - camPos.y - player.sleepCurlUp * 4f + Mathf.Lerp(0.5f, 1f, player.aerobicLevel) * num * (1f - num2);
            · sLeaser.sprites[0].rotation = Custom.AimFromOneVectorToAnother(vector2, vector);
            · sLeaser.sprites[0].scaleX = 1.4f + Mathf.Lerp(Mathf.Lerp(Mathf.Lerp(-0.05f, -0.15f, malnourished), 0.05f, num) * num2, 0.15f, player.sleepCurlUp);
            · sLeaser.sprites[0].scaleX = 0.76f + Mathf.Lerp(Mathf.Lerp(Mathf.Lerp(-0.05f, -0.15f, malnourished), 0.05f, num) * num2, 0.15f, player.sleepCurlUp);
            · sLeaser.sprites[0].scaleX = 1f + Mathf.Lerp(Mathf.Lerp(Mathf.Lerp(-0.05f, -0.15f, malnourished), 0.05f, num) * num2, 0.15f, player.sleepCurlUp);
            · sLeaser.sprites[0].scaleX = 0.9f + 0.2f * Mathf.Lerp(player.npcStats.Wideness, 0.5f, player.playerState.isPup ? 0.5f : 0f) + player.sleepCurlUp * 0.2f
            · sLeaser.sprites[0].alpha = ((!(player.watcherMorph > 0.25f)) ? 1 : 0);
  num2  num2                   Futile_White               -          
            · sLeaser.sprites[num2] = new FSprite("Futile_White");
            · sLeaser.sprites[num2].scale = 7f;
     i  i                      ?                          -          
            · sLeaser.sprites[i].color = color2;
     j  j                      ?                          -          
     m  m                      ?                          -          
     n  n                      pixel                      1x1        
            · sLeaser.sprites[n] = fSprite;
            · sLeaser.sprites[n].alpha = rubberAlphaPips;
            · sLeaser.sprites[n].x = vector19.x;
            · sLeaser.sprites[n].y = vector19.y;
 num24  num24                  ?                          -          
            · sLeaser.sprites[num24].x = vector20.x - camPos.x;
            · sLeaser.sprites[num24].y = vector20.y - camPos.y;
 num25  num25                  ?                          -          
            · sLeaser.sprites[num25].color = new Color(Mathf.Min(1f, color5.r * (1f - darkenFactor) + 0.01f), Mathf.Min(1f, color5.g * (1f - darkenFactor) + 0.01f),
 num26  num26                  ?                          -          
            · sLeaser.sprites[num26].alpha = 1f - player.dissolved;
 num27  num27                  ?                          -          
            · sLeaser.sprites[num27].alpha = 1f - player.camoProgress;
startSprite + 1  startSprite + 1        TriangleMesh([segments.GetLength(0]) -          
            · sLeaser.sprites[startSprite + 1] = TriangleMesh.MakeLongMesh(segments.GetLength(0), pointyTip: false, customColor: false);
            · sLeaser.sprites[startSprite + 1].alpha = 1f / (float)segments.GetLength(0);
            · sLeaser.sprites[startSprite + 1] = new FSprite("Futile_White");
            · sLeaser.sprites[startSprite + 1].x = vector.x - camPos.x;
            · sLeaser.sprites[startSprite + 1].y = vector.y - camPos.y;
            · sLeaser.sprites[startSprite + 1].color = color;
            · sLeaser.sprites[startSprite + 1].alpha = num * 0.5f * globalAlpha;
            · sLeaser.sprites[startSprite + 1].scale = 20f * num * 1f / 16f;
haloFirstSprite + 1  haloFirstSprite + 1    Futile_White")
			{
				shader = rCam.game.rainWorld.Shaders["FlatLightNoisy"]
			} -          
            · sLeaser.sprites[haloFirstSprite + 1].scale = 400f * num3 / 16f;
            · sLeaser.sprites[haloFirstSprite + 1].alpha = 0.1f * num13;
            · sLeaser.sprites[haloFirstSprite + 1] = new FSprite("Futile_White") { shader = rCam.game.rainWorld.Shaders["FlatLightNoisy"] };
            · sLeaser.sprites[haloFirstSprite + 1].color = RainWorld.GoldRGB;
            · sLeaser.sprites[haloFirstSprite + 1].alpha = 0f;
     1  1                      HipsA                      14x20      
            · sLeaser.sprites[1] = new FSprite("HipsA");
            · sLeaser.sprites[1].scaleX = 0.9f + 0.2f * Mathf.Lerp(player.npcStats.Wideness, 0.5f, player.playerState.isPup ? 0.5f : 0f) + Mathf.Lerp(Mathf.Lerp(Mat
            · sLeaser.sprites[1].x = (vector2.x * 2f + vector.x) / 3f - camPos.x;
            · sLeaser.sprites[1].y = (vector2.y * 2f + vector.y) / 3f - camPos.y - player.sleepCurlUp * 3f;
            · sLeaser.sprites[1].rotation = Custom.AimFromOneVectorToAnother(vector, Vector2.Lerp(tail[0].lastPos, tail[0].pos, timeStacker));
            · sLeaser.sprites[1].scaleY = 1f + player.sleepCurlUp * 0.2f;
            · sLeaser.sprites[1].scaleX = 1.6f + player.sleepCurlUp * 0.2f + 0.05f * num - 0.05f * malnourished;
            · sLeaser.sprites[1].scaleX = 0.76f + player.sleepCurlUp * 0.2f + 0.05f * num - 0.05f * malnourished;
            · sLeaser.sprites[1].scaleX = 1f + player.sleepCurlUp * 0.2f + 0.05f * num - 0.05f * malnourished;
            · sLeaser.sprites[1].alpha = ((!(player.watcherMorph > 0.15f)) ? 1 : 0);
startSprite + 2  startSprite + 2        BodyPearl                  6x6        
            · sLeaser.sprites[startSprite + 2] = new FSprite("BodyPearl");
            · sLeaser.sprites[startSprite + 2].color = Color.white;
            · sLeaser.sprites[startSprite + 2].alpha = 0.25f;
            · sLeaser.sprites[startSprite + 2].color = Color.white;
            · sLeaser.sprites[startSprite + 2].alpha = (1f - num2 / 10f) * 0.2f;
            · sLeaser.sprites[startSprite + 2].alpha = 0.25f;
            · sLeaser.sprites[startSprite + 2].x = sLeaser.sprites[startSprite].x;
            · sLeaser.sprites[startSprite + 2].y = sLeaser.sprites[startSprite].y;
            · sLeaser.sprites[startSprite + 2].scaleX = sLeaser.sprites[startSprite].scaleX;
            · sLeaser.sprites[startSprite + 2].scaleY = sLeaser.sprites[startSprite].scaleY;
            · sLeaser.sprites[startSprite + 2].rotation = sLeaser.sprites[startSprite].rotation;
     2  2                      triangleMesh               -          
            · sLeaser.sprites[2] = triangleMesh;
            · sLeaser.sprites[2].alpha = ((!(player.watcherMorph > 0f)) ? 1 : 0);
     3  3                      _cachedHeads[2, num7]      -          
            · sLeaser.sprites[3] = new FSprite("HeadB0");
            · sLeaser.sprites[3] = new FSprite("HeadA0");
            · sLeaser.sprites[3].x = vector3.x - camPos.x;
            · sLeaser.sprites[3].y = vector3.y - camPos.y;
            · sLeaser.sprites[3].rotation = num6;
            · sLeaser.sprites[3].scaleX = ((num6 < 0f) ? (-1f) : 1f);
            · sLeaser.sprites[3].element = Futile.atlasManager.GetElementWithName(_cachedHeads[2, num7]);
            · sLeaser.sprites[3].element = Futile.atlasManager.GetElementWithName(_cachedHeads[1, num7]);
            · sLeaser.sprites[3].element = Futile.atlasManager.GetElementWithName(_cachedHeads[0, num7]);
            · sLeaser.sprites[3].alpha = ((!(player.watcherMorph > 0.5f)) ? 1 : 0);
     4  4                      elementName                -          
            · sLeaser.sprites[4] = new FSprite("LegsA0");
            · sLeaser.sprites[4].x = vector11.x - camPos.x;
            · sLeaser.sprites[4].y = vector11.y - camPos.y;
            · sLeaser.sprites[4].rotation = Custom.AimFromOneVectorToAnother(legsDirection, new Vector2(0f, 0f));
            · sLeaser.sprites[4].scaleX = ((player.flipDirection > 0) ? 1 : (-1));
            · sLeaser.sprites[4].scaleX = ((player.flipDirection > 0) ? 1 : (-1));
            · sLeaser.sprites[4].scaleX = -1f;
            · sLeaser.sprites[4].scaleX = 1f;
            · sLeaser.sprites[4].scaleX = ((player.flipDirection > 0) ? 1 : (-1));
            · sLeaser.sprites[4].scaleX = ((player.flipDirection > 0) ? 1 : (-1));
            · sLeaser.sprites[4].y = Mathf.Clamp(sLeaser.sprites[4].y, vector2.y - 6f - camPos.y, vector2.y + 4f - camPos.y);
            · sLeaser.sprites[4].scaleX = ((player.flipDirection > 0) ? 1 : (-1));
            · sLeaser.sprites[4].scaleX = ((player.flipDirection > 0) ? 1 : (-1));
            · sLeaser.sprites[4].element = Futile.atlasManager.GetElementWithName(elementName);
     5  5                      PlayerArm0                 5x5        
            · sLeaser.sprites[5] = new FSprite("PlayerArm0");
            · sLeaser.sprites[5].scaleY = -1f;
 5 + j  5 + j                  _cachedPlayerArms[Mathf.RoundToInt(Mathf.Clamp(Vector2.Distance(vector12, vector13) / 2f, 0f, 12f))] -          
            · sLeaser.sprites[5 + j].x = vector12.x - camPos.x;
            · sLeaser.sprites[5 + j].y = vector12.y - camPos.y;
            · sLeaser.sprites[5 + j].element = Futile.atlasManager.GetElementWithName(_cachedPlayerArms[Mathf.RoundToInt(Mathf.Clamp(Vector2.Distance(vector12, vect
            · sLeaser.sprites[5 + j].rotation = Custom.AimFromOneVectorToAnother(vector12, vector13) + 90f;
            · sLeaser.sprites[5 + j].scaleY = ((vector.x < vector2.x) ? (-1f) : 1f);
            · sLeaser.sprites[5 + j].scaleY = ((player.flipDirection == -1) ? (-1f) : 1f);
            · sLeaser.sprites[5 + j].scaleY = Mathf.Sign(Custom.DistanceToLine(vector12, vector, vector2));
            · sLeaser.sprites[5 + j].scaleY = ((j == 0) ? 1f : (-1f));
     6  6                      PlayerArm0                 5x5        
            · sLeaser.sprites[6] = new FSprite("PlayerArm0");
     7  7                      "OnTopOfTerrainHand"       -          
            · sLeaser.sprites[7] = new FSprite("OnTopOfTerrainHand");
            · sLeaser.sprites[7].element = Futile.atlasManager.GetElementWithName("OnTopOfTerrainHand");
            · sLeaser.sprites[7].element = Futile.atlasManager.GetElementWithName("OnTopOfTerrainHand2");
            · sLeaser.sprites[7].element = Futile.atlasManager.GetElementWithName("OnTopOfTerrainHand");
 7 + j  7 + j                  ?                          -          
            · sLeaser.sprites[7 + j].x = vector12.x - camPos.x;
            · sLeaser.sprites[7 + j].y = vector12.y - camPos.y + ((player.animation != Player.AnimationIndex.ClimbOnBeam && player.animation != Player.AnimationInde
     8  8                      "OnTopOfTerrainHand"       -          
            · sLeaser.sprites[8] = new FSprite("OnTopOfTerrainHand");
            · sLeaser.sprites[8].scaleX = -1f;
            · sLeaser.sprites[8].element = Futile.atlasManager.GetElementWithName("OnTopOfTerrainHand");
            · sLeaser.sprites[8].element = Futile.atlasManager.GetElementWithName("OnTopOfTerrainHand2");
            · sLeaser.sprites[8].element = Futile.atlasManager.GetElementWithName("OnTopOfTerrainHand");
     9  9                      DefaultFaceSprite(sLeaser.sprites[9].scaleX, Custom.IntClamp((int)Mathf.Lerp(num7, 1f, player.sleepCurlUp), 0, 8)) -          
            · sLeaser.sprites[9] = new FSprite("FaceA0");
            · sLeaser.sprites[9].scaleX = Mathf.Sign(vector.x - vector2.x);
            · sLeaser.sprites[9].element = Futile.atlasManager.GetElementWithName(DefaultFaceSprite(sLeaser.sprites[9].scaleX, Custom.IntClamp((int)Mathf.Lerp(num7,
            · sLeaser.sprites[9].rotation = num6 * (1f - player.sleepCurlUp);
            · sLeaser.sprites[9].rotation = num6;
            · sLeaser.sprites[9].element = Futile.atlasManager.GetElementWithName(DefaultFaceSprite(sLeaser.sprites[9].scaleX, 0));
            · sLeaser.sprites[9].element = Futile.atlasManager.GetElementWithName(player.dead ? "FaceDead" : "FaceStunned");
            · sLeaser.sprites[9].scaleX = Mathf.Sign(vector.x - vector2.x);
            · sLeaser.sprites[9].scaleX = ((num6 < 0f) ? (-1f) : 1f);
            · sLeaser.sprites[9].element = Futile.atlasManager.GetElementWithName(DefaultFaceSprite(sLeaser.sprites[9].scaleX, 4));
            · sLeaser.sprites[9].scaleX = ((num6 < 0f) ? (-1f) : 1f);
            · sLeaser.sprites[9].scaleX = Mathf.Sign(vector9.x);
            · sLeaser.sprites[9].element = Futile.atlasManager.GetElementWithName(DefaultFaceSprite(sLeaser.sprites[9].scaleX, Mathf.RoundToInt(Mathf.Abs(Custom.Aim
            · sLeaser.sprites[9].rotation = 0f;
            · sLeaser.sprites[9].element = Futile.atlasManager.GetElementWithName(player.dead ? "FaceDead" : "FaceStunned");
            · sLeaser.sprites[9].rotation = num6;
            · sLeaser.sprites[9].element = Futile.atlasManager.GetElementWithName(DefaultFaceSprite(sLeaser.sprites[9].scaleX, 5));
            · sLeaser.sprites[9].rotation = num6 + 0.2f;
            · sLeaser.sprites[9].x = vector3.x + vector9.x - camPos.x;
            · sLeaser.sprites[9].y = vector3.y + vector9.y - 2f - camPos.y;
            · sLeaser.sprites[9].color = Color.white;
            · sLeaser.sprites[9].color = color;
            · sLeaser.sprites[9].color = Custom.HSL2RGB(UnityEngine.Random.value, UnityEngine.Random.value, UnityEngine.Random.value);
            · sLeaser.sprites[9].color = color2;
            · sLeaser.sprites[9].alpha = ((!(player.watcherMorph > 0.5f)) ? 1 : 0);
    10  10                     Futile_White               -          
            · sLeaser.sprites[10] = new FSprite("Futile_White");
            · sLeaser.sprites[10].x = vector14.x - camPos.x;
            · sLeaser.sprites[10].y = vector14.y - camPos.y;
            · sLeaser.sprites[10].alpha = 0.2f * Mathf.Lerp(lastMarkAlpha, markAlpha, timeStacker);
            · sLeaser.sprites[10].scale = 1f + Mathf.Lerp(lastMarkAlpha, markAlpha, timeStacker);
            · sLeaser.sprites[10].alpha = 0f;
            · sLeaser.sprites[10].color = color;
    11  11                     pixel                      1x1        
            · sLeaser.sprites[11] = new FSprite("pixel");
            · sLeaser.sprites[11].scale = 5f;
            · sLeaser.sprites[11].x = vector14.x - camPos.x;
            · sLeaser.sprites[11].y = vector14.y - camPos.y;
            · sLeaser.sprites[11].alpha = Mathf.Lerp(lastMarkAlpha, markAlpha, timeStacker);
            · sLeaser.sprites[11].alpha = 0f;
            · sLeaser.sprites[11].color = Color.Lerp(color, Color.white, 0.3f);
    12  12                     TriangleMesh([ropeSegments.Length - 1, pointyTip: false, customColor: true]) -          
            · sLeaser.sprites[12] = new FSprite("MushroomA");
            · sLeaser.sprites[12] = TriangleMesh.MakeLongMesh(ropeSegments.Length - 1, pointyTip: false, customColor: true);
            · sLeaser.sprites[12].rotation = sLeaser.sprites[9].rotation;
            · sLeaser.sprites[12].scaleX = 1f;
            · sLeaser.sprites[12].x = sLeaser.sprites[9].x + vector18.x;
            · sLeaser.sprites[12].y = sLeaser.sprites[9].y + vector18.y;
            · sLeaser.sprites[12].scaleX = 1f - (float)num14 / 8f;
            · sLeaser.sprites[12].x = sLeaser.sprites[9].x + 3f + 4f * ((float)num14 / 8f);
            · sLeaser.sprites[12].x = sLeaser.sprites[9].x + 3f * (1f - (float)num14 / 8f);
            · sLeaser.sprites[12].x = sLeaser.sprites[9].x + 3f * (1f - (float)num14 / 8f);
            · sLeaser.sprites[12].y = sLeaser.sprites[9].y + 3f;
            · sLeaser.sprites[12].x = Mathf.Lerp(mainBodyChunk.lastPos.x, mainBodyChunk.pos.x, timeStacker) - camPos.x;
            · sLeaser.sprites[12].y = Mathf.Lerp(mainBodyChunk.lastPos.y, mainBodyChunk.pos.y, timeStacker) - camPos.y;
            · sLeaser.sprites[12].color = new Color(player.camoProgress, 0f, 0f);
            · sLeaser.sprites[12].color = JollyColor(player.playerState.playerNumber, 2);
            · sLeaser.sprites[12].color = CustomColorSafety(2);
            · sLeaser.sprites[12].color = new Color(0.27059f, 0.15686f, 0.23529f);
            · sLeaser.sprites[12].color = new Color(0.651f, 0.5569f, 0.5922f);
            · sLeaser.sprites[12].color = Color.Lerp(color2, new Color(0.5647f, 0.3451f, 0.0118f), 0.5f);
            · sLeaser.sprites[12].color = new Color(0.4353f, 0.302f, 0.4f);
            · sLeaser.sprites[12].color = new Color(0.098f, 0.0314f, 0.1765f);
    13  13                     Futile_White               -          
            · sLeaser.sprites[13] = new FSprite("Futile_White");
            · sLeaser.sprites[13].x = sLeaser.sprites[3].x + player.burstX;
            · sLeaser.sprites[13].y = sLeaser.sprites[3].y + player.burstY + 60f;
            · sLeaser.sprites[13].scale = Mathf.Lerp(50f, 2f, Mathf.Pow(f, 0.5f));
            · sLeaser.sprites[13].alpha = Mathf.Pow(f, 3f);
    14  14                     guardEye                   24x24      
            · sLeaser.sprites[14] = new FSprite("guardEye");
            · sLeaser.sprites[14].x = rubberMarkX;
            · sLeaser.sprites[14].y = rubberMarkY + 60f;
            · sLeaser.sprites[14].color = sLeaser.sprites[9].color;
            · sLeaser.sprites[14].x = rubberMarkX + rubberMouseX;
            · sLeaser.sprites[14].y = rubberMarkY + 60f + rubberMouseY;
            · sLeaser.sprites[14].alpha = rubberAlphaEmblem;
15 + k  15 + k                 WormEye                    4x4        
            · sLeaser.sprites[15 + k] = new FSprite("WormEye");
15 + m  15 + m                 ?                          -          
            · sLeaser.sprites[15 + m].scale = 0f;
            · sLeaser.sprites[15 + m].scale = 1f;
            · sLeaser.sprites[15 + m].scale = (player.godTimer - num20) / num19;
            · sLeaser.sprites[15 + m].color = sLeaser.sprites[9].color;
            · sLeaser.sprites[15 + m].color = SlugcatColor(CharacterForColor);
num + scalesPositions.Length  num + scalesPositions.Length LizardScaleB" + graphic    -          
            · sLeaser.sprites[num + scalesPositions.Length] = new FSprite("LizardScaleB" + graphic);
            · sLeaser.sprites[num + scalesPositions.Length].scaleY = scaleObjects[num - startSprite].length / graphicHeight;
            · sLeaser.sprites[num + scalesPositions.Length].x = p.x - camPos.x;
            · sLeaser.sprites[num + scalesPositions.Length].y = p.y - camPos.y;
            · sLeaser.sprites[num + scalesPositions.Length].rotation = Custom.AimFromOneVectorToAnother(p, Vector2.Lerp(scaleObjects[num - startSprite].lastPos, sca
            · sLeaser.sprites[num + scalesPositions.Length].scaleX = scaleObjects[num - startSprite].width * Mathf.Sign(f);
            · sLeaser.sprites[num + scalesPositions.Length].color = effectColor;
num3 + scalesPositions.Length  num3 + scalesPositions.Length ?                          -          
            · sLeaser.sprites[num3 + scalesPositions.Length].color = Color.Lerp(effectColor, baseColor, pGraphics.malnourished / 1.75f);
15 + numGodPips + tentacles.Length * 2  15 + numGodPips + tentacles.Length * 2 Futile_White               -          
            · sLeaser.sprites[15 + numGodPips + tentacles.Length * 2] = new FSprite("Futile_White");
            · sLeaser.sprites[15 + numGodPips + tentacles.Length * 2].x = sLeaser.sprites[1].x;
            · sLeaser.sprites[15 + numGodPips + tentacles.Length * 2].y = sLeaser.sprites[1].y;
            · sLeaser.sprites[15 + numGodPips + tentacles.Length * 2].scale = 15f * darkenFactor;


## 爆炸特效（ExplosionLight）

!! 找不到 work/scratch/decomp_full/ExplosionLight.cs


## 2026-10 大改：蛞蝓猫/蜥蜴/幼崽对拍

- `Player.cs:4114-4131,4641-4645`：幼崽只缩短体节连接（17→12），保留体块半径 9/8；`PlayerGraphics.cs:2687,2878-3041`：仅 BodyA 竖向压缩并使用 RenderAsPup 胸部插值和专用站立偏移。
- `Lizard.cs` / `LizardAI.cs` 的 Climb/MovementConnection：实体墙、背景墙、杆统一为带 kind 的附着面；杆为 Climb tile，不作为 Solid。
- `Player.cs` 的能力边界：Saint `no_spear` 在身体拾取与背槽入口统一拦截。

## 2026-10 音频与交互补全

- `RoomRain.cs:391-400`：Normal/Heavy/Death 雨声按 intensity 平滑更新；`SoundManager` 用独立 `rain_loop.wav` 循环并按雨势渐变。`SoundID.cs` 的 `Lizard_Jaws_Bite_Do_Damage`、`UI_Slugcat_Stunned_*` 对应咬合与眩晕音效入口。
- Push To Meow `sounds.txt`：猫叫按 `vol=0.6,maxPitch=1.1,minPitch=0.9`，并按 Normal/Pup/Whispery/Coarse/Spear/Fat/Rivulet/Watcher 音色族取样；播放器改为每次独立 `QSoundEffect`，避免长叫被重启截断。
- 抓取/甩动调用猫叫事件；仅实际发声时有抬头与呼声反馈，抓取本身不强制闭眼。高处落地调用 `apply_stun(drop_items=True,crawl=True)`，先掉手持物并直接进入匍匐。
- 放置杆、墙、庇护所释放使用 `mouseReleaseEvent` 坐标，幼崽预览不再跑一帧重力。
