using System.Collections.Generic;
using Tcg.Board;
using Tcg.View;
using TMPro;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.InputSystem.UI;
using UnityEngine.SceneManagement;
using UnityEngine.TextCore.LowLevel;
using UnityEngine.UI;

/// <summary>
/// Builds the client's generated assets from code: sprite import settings, TextMeshPro font
/// assets, the card prefab and the board scene, all laid out from the mockup in
/// docs/client-design.md (CSS px = canvas units at the 1280x720 reference).
/// TCG > Rebuild Client Assets regenerates them, replacing hand edits to the prefab and scene.
/// </summary>
public static class ClientAssetBuilder
{
    const string ArtDir = "Assets/Art/Generated";
    const string FontDir = "Assets/Fonts";
    const string PrefabPath = "Assets/Prefabs/Card.prefab";
    const string ScenePath = "Assets/Scenes/Main.unity";
    const float SpritePpu = 400f;   // 4 texture px per canvas unit
    const float SliceRadius = 16f;  // corner radius baked into rounded.png
    const string Charset =
        " !\"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~·…’→⟳❄−•";
    static readonly string[] ArtNames = { "knight", "beast", "mage", "golem" };

    class Fonts
    {
        public TMP_FontAsset Lilita, Nunito, NunitoBlack, NunitoItalic;
        public Material LilitaOutline;
    }

    const string ThemePath = "Assets/Art/UiTheme.asset";
    static Sprite _glow;

    [MenuItem("TCG/Rebuild Client Assets")]
    public static void BuildAll()
    {
        ImportSprites();
        var fonts = BuildFonts();
        var theme = BuildTheme(fonts);
        Ui.Theme = theme;
        var card = BuildCardPrefab(fonts);
        BuildBoardScene(fonts, card, theme);
        AssetDatabase.SaveAssets();
        Debug.Log("TCG client assets rebuilt");
    }

    // --- sprites

    static void ImportSprites()
    {
        AssetDatabase.Refresh();
        foreach (var guid in AssetDatabase.FindAssets("t:Texture2D", new[] { ArtDir }))
        {
            string path = AssetDatabase.GUIDToAssetPath(guid);
            var ti = (TextureImporter)AssetImporter.GetAtPath(path);
            string file = System.IO.Path.GetFileNameWithoutExtension(path);
            ti.textureType = TextureImporterType.Sprite;
            ti.spriteImportMode = SpriteImportMode.Single;
            ti.mipmapEnabled = false;
            ti.alphaIsTransparency = true;
            ti.textureCompression = TextureImporterCompression.Uncompressed;
            ti.filterMode = FilterMode.Bilinear;
            ti.wrapMode = file == "field_tile" || file == "stripes" ? TextureWrapMode.Repeat : TextureWrapMode.Clamp;
            ti.spritePixelsPerUnit = file.StartsWith("field") ? 100f : SpritePpu;
            var settings = new TextureImporterSettings();
            ti.ReadTextureSettings(settings);
            settings.spriteMeshType = SpriteMeshType.FullRect;
            ti.SetTextureSettings(settings);
            float border = file == "rounded" || file == "ring" ? SliceRadius * 4f : file == "glow" ? 40f * 4f : 0f;
            ti.spriteBorder = new Vector4(border, border, border, border);
            ti.SaveAndReimport();
        }
        _glow = Sprite("glow");
    }

    static UiTheme BuildTheme(Fonts f)
    {
        var theme = AssetDatabase.LoadAssetAtPath<UiTheme>(ThemePath);
        if (theme == null)
        {
            theme = ScriptableObject.CreateInstance<UiTheme>();
            AssetDatabase.CreateAsset(theme, ThemePath);
        }
        theme.Rounded = Sprite("rounded");
        theme.Ring = Sprite("ring");
        theme.Glow = Sprite("glow");
        theme.Dot = Sprite("dot");
        theme.TargetRing = Sprite("target_ring");
        theme.ArrowHead = Sprite("arrow_head");
        theme.Stripes = Sprite("stripes");
        theme.GemFill = Sprite("gem_fill");
        theme.GemRim = Sprite("gem_rim");
        theme.GemShine = Sprite("gem_shine");
        theme.GemDashed = Sprite("gem_dashed");
        theme.Crown = Sprite("crown");
        theme.Lilita = f.Lilita;
        theme.Nunito = f.Nunito;
        theme.NunitoBlack = f.NunitoBlack;
        theme.LilitaOutline = f.LilitaOutline;
        EditorUtility.SetDirty(theme);
        AssetDatabase.SaveAssets();
        return theme;
    }

    static Sprite Sprite(string name) => AssetDatabase.LoadAssetAtPath<Sprite>($"{ArtDir}/{name}.png");

    // --- fonts

    static Fonts BuildFonts()
    {
        var f = new Fonts
        {
            Lilita = FontAsset("LilitaOne-Regular.ttf", "LilitaOne SDF"),
            Nunito = FontAsset("Nunito-Bold.ttf", "Nunito Bold SDF"),
            NunitoBlack = FontAsset("Nunito-Black.ttf", "Nunito Black SDF"),
        };
        var italic = f.NunitoItalic = FontAsset("Nunito-BoldItalic.ttf", "Nunito BoldItalic SDF");
        // Body text is Nunito 700; <b> (keywords, triggers) is 900 and <i> (flavour) the 700 italic.
        f.Nunito.fontWeightTable[7].regularTypeface = f.NunitoBlack;
        f.Nunito.fontWeightTable[4].italicTypeface = italic;
        EditorUtility.SetDirty(f.Nunito);

        // Lilita One and Nunito lack ⟳ (activated abilities) and → (previews): fall back to DejaVu Sans.
        var symbols = FontAsset("DejaVuSans-Bold.ttf", "DejaVuSans Bold SDF");
        foreach (var font in new[] { f.Lilita, f.Nunito, f.NunitoBlack, italic })
        {
            font.fallbackFontAssetTable ??= new List<TMP_FontAsset>();
            if (!font.fallbackFontAssetTable.Contains(symbols)) font.fallbackFontAssetTable.Add(symbols);
            EditorUtility.SetDirty(font);
        }

        // White numbers and names with a dark outline and a drop shadow below.
        string path = $"{FontDir}/LilitaOne Outline.mat";
        var m = AssetDatabase.LoadAssetAtPath<Material>(path);
        if (m == null)
        {
            m = new Material(f.Lilita.material);
            AssetDatabase.CreateAsset(m, path);
        }
        m.shader = f.Lilita.material.shader;
        m.SetTexture(ShaderUtilities.ID_MainTex, f.Lilita.material.GetTexture(ShaderUtilities.ID_MainTex));
        m.SetFloat(ShaderUtilities.ID_GradientScale, f.Lilita.material.GetFloat(ShaderUtilities.ID_GradientScale));
        m.SetColor(ShaderUtilities.ID_OutlineColor, Palette.Outline);
        m.SetFloat(ShaderUtilities.ID_OutlineWidth, 0.28f);
        m.SetFloat(ShaderUtilities.ID_FaceDilate, 0.22f);
        m.EnableKeyword(ShaderUtilities.Keyword_Underlay);
        m.SetColor(ShaderUtilities.ID_UnderlayColor, Palette.Outline);
        m.SetFloat(ShaderUtilities.ID_UnderlayOffsetX, 0f);
        m.SetFloat(ShaderUtilities.ID_UnderlayOffsetY, -0.6f);
        m.SetFloat(ShaderUtilities.ID_UnderlayDilate, 0.5f);
        m.SetFloat(ShaderUtilities.ID_UnderlaySoftness, 0f);
        EditorUtility.SetDirty(m);
        f.LilitaOutline = m;
        AssetDatabase.SaveAssets();
        return f;
    }

    static TMP_FontAsset FontAsset(string ttf, string name)
    {
        string path = $"{FontDir}/{name}.asset";
        var existing = AssetDatabase.LoadAssetAtPath<TMP_FontAsset>(path);
        if (existing != null) return existing;
        var font = AssetDatabase.LoadAssetAtPath<Font>($"{FontDir}/{ttf}");
        var fa = TMP_FontAsset.CreateFontAsset(font, 90, 9, GlyphRenderMode.SDFAA, 1024, 1024,
            AtlasPopulationMode.Dynamic, false);
        fa.name = name;
        AssetDatabase.CreateAsset(fa, path);
        fa.atlasTextures[0].name = name + " Atlas";
        AssetDatabase.AddObjectToAsset(fa.atlasTextures[0], fa);
        fa.material.name = name + " Material";
        AssetDatabase.AddObjectToAsset(fa.material, fa);
        fa.TryAddCharacters(Charset, out _);
        EditorUtility.SetDirty(fa);
        AssetDatabase.SaveAssets();
        return fa;
    }

    // --- the card

    static CardView BuildCardPrefab(Fonts f)
    {
        var root = new GameObject("Card", typeof(RectTransform));
        root.layer = 5;
        var rootRt = (RectTransform)root.transform;
        rootRt.sizeDelta = new Vector2(CardView.Width, CardView.Height);
        var cv = root.AddComponent<CardView>();
        root.AddComponent<CardInput>();
        cv.Group = root.AddComponent<CanvasGroup>();

        var visual = Stretch("Visual", rootRt, 0, 0, 0, 0);
        cv.Visual = visual;
        cv.GlowHalo = Img(Stretch("GlowHalo", visual, -27, -27, -27, -27), _glow, Color.white);
        cv.GlowHalo.type = Image.Type.Sliced;
        cv.GlowRing = Rounded(Stretch("GlowRing", visual, -3, -3, -3, -3), Color.white, 16);
        cv.GlowHalo.gameObject.SetActive(false);
        cv.GlowRing.gameObject.SetActive(false);
        cv.TargetOutline = Ui.Outline(Stretch("TargetRing", visual, -7, -7, -7, -7), Palette.GlowTarget, 16);
        cv.TargetOutline.gameObject.SetActive(false);
        Rounded(Stretch("Shadow", visual, 0, 5, 0, -5), Palette.CardShadow, 13);
        Rounded(Stretch("Body", visual, 0, 0, 0, 0), Palette.CardNavy, 13).raycastTarget = true;  // taps and drags
        cv.FrameEdge = Rounded(Stretch("FrameEdge", visual, 4, 4, 4, 6), Palette.Aspect(1), 10);
        var frame = Stretch("Frame", cv.FrameEdge.rectTransform, 2, 2, 2, 2);
        Rounded(frame, Palette.TextBox, 8);
        frame.gameObject.AddComponent<Mask>().showMaskGraphic = true;

        var artSprites = new List<Sprite>();
        for (int a = 1; a <= 6; a++)
            foreach (var n in ArtNames) artSprites.Add(Sprite($"art_{a}_{n}"));
        cv.ArtSprites = artSprites.ToArray();
        cv.Art = Img(Box("Art", frame, 0, 0, 138, 92), artSprites[2], Color.white);

        // A unit that has attacked: the art just dims (the glow on units that can attack does the rest).
        var exhausted = Box("Exhausted", frame, 0, 0, 138, 92);
        Img(exhausted, null, Palette.Exhausted);
        cv.ExhaustedOverlay = exhausted.gameObject;
        exhausted.gameObject.SetActive(false);

        // Frozen: ice over the art. Hidden (Elusive, not attacked yet): a misty veil.
        var frozen = Box("Frozen", frame, 0, 0, 138, 92);
        Img(frozen, null, Palette.Hex("#BDEBFF").WithAlpha(0.55f));
        Text(Stretch("Flake", frozen, 0, 0, 0, 0), "❄", f.Lilita, 34, Palette.Hex("#F2FBFF"),
            TextAlignmentOptions.Center, f.LilitaOutline);
        cv.FrozenOverlay = frozen.gameObject;
        frozen.gameObject.SetActive(false);
        var hidden = Box("Hidden", frame, 0, 0, 138, 92);
        Img(hidden, null, Palette.Hex("#C9C2F2").WithAlpha(0.45f));
        cv.HiddenOverlay = hidden.gameObject;
        hidden.gameObject.SetActive(false);

        // The name banner, with room for the subtitle line under the name.
        var banner = Box("Banner", frame, 0, 78, 138, 28);
        Img(banner, null, Palette.CardNavy);
        cv.BannerFill = Img(Stretch("Fill", banner, 0, 2, 0, 2), null, Palette.Aspect(1));
        var shine = Node("Shine", cv.BannerFill.rectTransform);
        shine.anchorMin = new Vector2(0, 1);
        shine.anchorMax = new Vector2(1, 1);
        shine.offsetMin = new Vector2(0, -3);
        shine.offsetMax = Vector2.zero;
        Img(shine, null, Color.white.WithAlpha(0.3f));
        cv.NameText = Text(Stretch("Name", banner, 3, 0, 3, 0), "Card name", f.Lilita, 13, Color.white,
            TextAlignmentOptions.Center, f.LilitaOutline);
        cv.NameText.enableAutoSizing = true;
        cv.NameText.fontSizeMin = 8;
        cv.NameText.fontSizeMax = 13;
        cv.SubtitleText = Text(Stretch("Subtitle", banner, 4, 15, 4, 2), "", f.NunitoItalic, 8.5f,
            Color.white.WithAlpha(0.92f), TextAlignmentOptions.Center);
        cv.SubtitleText.enableAutoSizing = true;
        cv.SubtitleText.fontSizeMin = 6.5f;
        cv.SubtitleText.fontSizeMax = 8.5f;

        cv.BodyText = Text(Box("Text", frame, 8, 108, 122, 64), "", f.Nunito, 11.5f, Palette.BodyText,
            TextAlignmentOptions.Center);
        cv.BodyText.textWrappingMode = TextWrappingModes.Normal;
        cv.BodyText.lineSpacing = -12f;

        var tag = Node("Traits", frame);
        Anchor(tag, new Vector2(0.5f, 0), new Vector2(0.5f, 0), new Vector2(0, 4), new Vector2(40, 14));
        Rounded(tag, Palette.CardNavy, 6);
        var tagLayout = tag.gameObject.AddComponent<HorizontalLayoutGroup>();
        tagLayout.padding = new RectOffset(8, 8, 0, 0);
        tagLayout.childControlWidth = tagLayout.childControlHeight = true;
        tagLayout.childForceExpandWidth = false;
        tagLayout.childForceExpandHeight = true;
        tag.gameObject.AddComponent<ContentSizeFitter>().horizontalFit = ContentSizeFitter.FitMode.PreferredSize;
        cv.TraitText = Text(Node("Text", tag), "Unit", f.NunitoBlack, 9, Palette.TraitText, TextAlignmentOptions.Center);
        cv.TraitText.margin = new Vector4(0, 0, 0, 1);
        cv.TraitText.characterSpacing = 4f;

        var cost = Box("Cost", visual, -7, -7, 36, 39);
        Img(Stretch("Fill", cost, 0, 0, 0, 0), Sprite("gem_fill"), Palette.Energy);
        Img(Stretch("Rim", cost, 0, 0, 0, 0), Sprite("gem_rim"), Palette.Outline);
        Img(Stretch("Shine", cost, 0, 0, 0, 0), Sprite("gem_shine"), Color.white.WithAlpha(0.6f));
        cv.CostText = Number(Stretch("Value", cost, 0, 0, 0, 1), f, 20);

        var sword = Img(Box("Power", visual, 70.3f, 48.5f, 68, 68), Sprite("sword"), Color.white);
        cv.PowerText = Number(Box("PowerValue", visual, 95.3f, 69.5f, 22, 22), f, 17);

        var heart = Img(Box("Health", visual, 120.2f, 65.7f, 36, 33), Sprite("heart"), Color.white);
        cv.HealthText = Number(Box("HealthValue", visual, 120.2f, 65.7f, 36, 29), f, 18);
        cv.UnitOnly = new[] { sword.gameObject, cv.PowerText.gameObject, heart.gameObject, cv.HealthText.gameObject };

        // A unit with a usable ⟳ ability: a small gold disc on the top edge.
        var marker = Box("AbilityMarker", visual, 63, -9, 24, 24);
        Img(marker, Ui.Theme.Dot, Palette.Outline);
        Img(Stretch("Face", marker, 2, 2, 2, 2), Ui.Theme.Dot, Palette.Gold);
        var glyph = Text(Stretch("Glyph", marker, 0, 0, 0, 1), "⟳", f.NunitoBlack, 15, Palette.Outline, TextAlignmentOptions.Center);
        glyph.fontStyle = FontStyles.Bold;
        cv.AbilityMarker = marker.gameObject;
        marker.gameObject.SetActive(false);

        System.IO.Directory.CreateDirectory("Assets/Prefabs");
        var prefab = PrefabUtility.SaveAsPrefabAsset(root, PrefabPath);
        Object.DestroyImmediate(root);
        return prefab.GetComponent<CardView>();
    }

    // --- the board

    static void BuildBoardScene(Fonts f, CardView cardPrefab, UiTheme theme)
    {
        var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);

        var cam = new GameObject("Main Camera", typeof(Camera));
        cam.tag = "MainCamera";
        var camera = cam.GetComponent<Camera>();
        camera.orthographic = true;
        camera.clearFlags = CameraClearFlags.SolidColor;
        camera.backgroundColor = Palette.UiNavy;
        cam.transform.position = new Vector3(0, 0, -10);

        new GameObject("EventSystem", typeof(EventSystem), typeof(InputSystemUIInputModule));

        var canvasGo = new GameObject("Canvas", typeof(Canvas), typeof(CanvasScaler), typeof(GraphicRaycaster));
        canvasGo.layer = 5;
        canvasGo.GetComponent<Canvas>().renderMode = RenderMode.ScreenSpaceOverlay;
        var scaler = canvasGo.GetComponent<CanvasScaler>();
        scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
        scaler.referenceResolution = new Vector2(1280, 720);
        scaler.screenMatchMode = CanvasScaler.ScreenMatchMode.Expand;  // wider screens get extra side space

        var board = Stretch("Board", canvasGo.transform, 0, 0, 0, 0);
        var bv = board.gameObject.AddComponent<BoardView>();
        bv.CardPrefab = cardPrefab;
        bv.Theme = theme;

        Img(Stretch("Background", board, 0, 0, 0, 0), null, Palette.UiNavy);
        var field = Img(Stretch("Field", board, 0, 0, 0, 0), Sprite("field_tile"), Color.white);
        field.type = Image.Type.Tiled;
        Img(Stretch("Fade", board, 0, 0, 0, 0), Sprite("field_fade"), Color.white);

        // Opponent's hand: card backs peeking in at the top centre.
        bv.OpponentBacks = Node("OpponentBacks", board);
        Anchor(bv.OpponentBacks, new Vector2(0.5f, 1), new Vector2(0.5f, 0.5f), new Vector2(0, 54), Vector2.zero);
        var back = Node("CardBack", bv.OpponentBacks);
        Anchor(back, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 1), Vector2.zero, new Vector2(62, 86));
        Rounded(Stretch("Shadow", back, 0, 4, 0, -4), Palette.CardShadow, 9);
        Rounded(Stretch("Border", back, 0, 0, 0, 0), Palette.Outline, 9);
        Rounded(Stretch("Ring", back, 3, 3, 3, 3), Palette.CardBackRing, 6);
        Rounded(Stretch("Face", back, 6, 6, 6, 6), Palette.CardBack, 3);
        bv.CardBackTemplate = back.gameObject;

        BuildOpponentBar(bv, board, f);

        // The field: both rows of units around a divider line.
        var divider = Node("Divider", board);
        divider.anchorMin = new Vector2(0, 1);
        divider.anchorMax = new Vector2(1, 1);
        divider.offsetMin = new Vector2(48, -272);
        divider.offsetMax = new Vector2(-48, -270);
        Img(divider, null, Palette.Outline.WithAlpha(0.2f));
        var line = Node("Line", board);
        line.anchorMin = new Vector2(0, 1);
        line.anchorMax = new Vector2(1, 1);
        line.offsetMin = new Vector2(48, -270);
        line.offsetMax = new Vector2(-48, -268);
        Img(line, null, Color.white.WithAlpha(0.5f));

        bv.OpponentUnits = Node("OpponentUnits", board);
        Anchor(bv.OpponentUnits, new Vector2(0.5f, 1), new Vector2(0.5f, 0.5f), new Vector2(0, -160.5f), Vector2.zero);
        bv.HumanUnits = Node("HumanUnits", board);
        Anchor(bv.HumanUnits, new Vector2(0.5f, 1), new Vector2(0.5f, 0.5f), new Vector2(0, -380.5f), Vector2.zero);

        BuildHumanHero(bv, board, f);
        BuildManaAndButtons(bv, board, f);

        bv.Hand = Node("Hand", board);
        Anchor(bv.Hand, new Vector2(0.5f, 0), new Vector2(0.5f, 0.5f), Vector2.zero, Vector2.zero);

        BuildMessages(bv, board, f);

        var net = new GameObject("Network").AddComponent<NetworkClient>();
        var game = new GameObject("Game").AddComponent<GameController>();
        game.Network = net;
        game.Board = bv;
        game.Interaction = board.gameObject.AddComponent<BoardInteraction>();
        game.Interaction.Board = bv;

        EditorSceneManager.SaveScene(scene, ScenePath);
        EditorBuildSettings.scenes = new[] { new EditorBuildSettingsScene(ScenePath, true) };
    }

    static void BuildOpponentBar(BoardView bv, RectTransform board, Fonts f)
    {
        // The enemy hero: portrait, name and a health bar. The whole panel is the attack_hero target.
        bv.OpponentHero = Box("OpponentHero", board, 12, 2, 300, 56);
        var ring = Ui.Outline(Stretch("TargetRing", bv.OpponentHero, -4, -4, -4, -4), Palette.GlowTarget, 16);
        ring.gameObject.SetActive(false);
        var avatar = Box("OpponentAvatar", board, 24, 8, 42, 42);
        bv.OpponentAvatarText = Avatar(avatar, Palette.OpponentAccent, Palette.OpponentLip, 10, 4, 16, f);

        bv.OpponentInfoText = Text(Box("OpponentInfo", board, 76, 9, 500, 20), "Opponent", f.NunitoBlack, 14,
            Color.white, TextAlignmentOptions.Left);
        Img(Box("OpponentHeart", board, 76, 29, 18, 17), Sprite("heart"), Color.white).preserveAspect = true;
        bv.OpponentHealthFill = Bar(Box("OpponentHealth", board, 100, 31, 140, 12), Palette.Health, 6, 4, 3);
        bv.OpponentHealthText = Number(Box("OpponentHealthText", board, 246, 26, 80, 21), f, 15);
        bv.OpponentHealthText.alignment = TextAlignmentOptions.Left;

        var mana = Node("OpponentMana", board);
        Anchor(mana, new Vector2(1, 1), new Vector2(1, 1), new Vector2(-24, -14), new Vector2(400, 22));
        bv.OpponentCrystals = GemRow(mana, new Vector2(18, 20), false);
        bv.OpponentManaText = Number(Node("Count", mana), f, 16);
        bv.OpponentManaText.rectTransform.sizeDelta = new Vector2(46, 22);
    }

    static void BuildHumanHero(BoardView bv, RectTransform board, Fonts f)
    {
        bv.HumanHero = Box("HumanHero", board, 12, 498, 290, 92, bottom: true);
        var avatar = Box("HumanAvatar", board, 24, 504, 48, 48, bottom: true);
        Avatar(avatar, Palette.HumanAccent, Palette.HumanLip, 11, 5, 18, f).text = UiText.YouAvatar;
        bv.HumanInfoText = Text(Box("HumanInfo", board, 82, 507, 180, 44, bottom: true), UiText.You, f.NunitoBlack, 15,
            Color.white, TextAlignmentOptions.TopLeft);
        bv.HumanInfoText.lineSpacing = -8f;
        Img(Box("HumanHeart", board, 24, 558, 22, 20, bottom: true), Sprite("heart"), Color.white).preserveAspect = true;
        bv.HumanHealthFill = Bar(Box("HumanHealth", board, 52, 560, 170, 16, bottom: true), Palette.Health, 8, 6, 4);
        bv.HumanHealthText = Number(Box("HumanHealthText", board, 228, 556, 80, 24, bottom: true), f, 18);
        bv.HumanHealthText.alignment = TextAlignmentOptions.Left;
    }

    static void BuildManaAndButtons(BoardView bv, RectTransform board, Fonts f)
    {
        var mana = Node("HumanMana", board);
        Anchor(mana, new Vector2(1, 0), new Vector2(1, 1), new Vector2(-24, 220), new Vector2(400, 28));
        bv.HumanCrystals = GemRow(mana, new Vector2(22, 24), true);
        bv.HumanManaText = Number(Node("Count", mana), f, 20);
        bv.HumanManaText.rectTransform.sizeDelta = new Vector2(58, 28);

        // The Spare Spore: the second player's one-off +1 mana, shown while its action is legal.
        var spore = Node("SpareSpore", board);
        Anchor(spore, new Vector2(1, 0), new Vector2(1, 1), new Vector2(-116, 190), new Vector2(190, 40));
        bv.SpareSporeButton = Ui.Button(spore, "SPARE SPORE", Palette.Hex("#9152E0"), Palette.Hex("#5B2E99"), 13,
            out bv.SpareSporeLabel, 10);
        bv.SpareSporeLabel.textWrappingMode = TextWrappingModes.Normal;  // the server's text is long
        bv.SpareSporeLabel.fontSizeMin = 8;
        spore.gameObject.SetActive(false);

        var pill = Node("Turn", board);
        Anchor(pill, new Vector2(1, 0), new Vector2(1, 1), new Vector2(-24, 182), new Vector2(80, 25));
        Rounded(pill, Palette.Gold, 14);
        var inner = Rounded(Stretch("Inner", pill, 2, 2, 2, 2), Palette.Outline, 12);
        inner.gameObject.AddComponent<LayoutElement>().ignoreLayout = true;
        var pillLayout = pill.gameObject.AddComponent<HorizontalLayoutGroup>();
        pillLayout.padding = new RectOffset(14, 14, 4, 4);
        pillLayout.childControlWidth = pillLayout.childControlHeight = true;
        pillLayout.childForceExpandWidth = pillLayout.childForceExpandHeight = false;
        var pillFit = pill.gameObject.AddComponent<ContentSizeFitter>();
        pillFit.horizontalFit = pillFit.verticalFit = ContentSizeFitter.FitMode.PreferredSize;
        bv.TurnText = Text(Node("Text", pill), "TURN 1", f.Lilita, 13, Palette.Gold, TextAlignmentOptions.Center);

        // A soft gold glow behind END TURN, pulsed by BoardView when nothing else is left to do.
        var glow = Node("EndTurnGlow", board);
        Anchor(glow, new Vector2(1, 0), new Vector2(1, 1), new Vector2(-2, 170), new Vector2(224, 102));
        bv.EndTurnGlow = Img(glow, _glow, Palette.Gold);
        bv.EndTurnGlow.type = Image.Type.Sliced;
        glow.gameObject.SetActive(false);

        var button = Node("EndTurn", board);
        Anchor(button, new Vector2(1, 0), new Vector2(1, 1), new Vector2(-24, 148), new Vector2(180, 58));
        Rounded(button, Palette.Outline, 14).raycastTarget = true;
        Rounded(Stretch("Lip", button, 3, 3, 3, 3), Palette.GoldLip, 11);
        var face = Rounded(Stretch("Face", button, 3, 3, 3, 9), Palette.Gold, 11);
        var shine = Node("Shine", face.rectTransform);
        shine.anchorMin = new Vector2(0, 1);
        shine.anchorMax = new Vector2(1, 1);
        shine.offsetMin = new Vector2(6, -5);
        shine.offsetMax = new Vector2(-6, -1);
        Rounded(shine, Color.white.WithAlpha(0.45f), 2);
        bv.EndTurnLabel = Text(Stretch("Label", button, 8, 3, 8, 9), "END TURN", f.Lilita, 22, Color.white,
            TextAlignmentOptions.Center, f.LilitaOutline);
        bv.EndTurnLabel.enableAutoSizing = true;
        bv.EndTurnLabel.fontSizeMin = 12;
        bv.EndTurnLabel.fontSizeMax = 22;
        bv.EndTurnButton = button.gameObject.AddComponent<Button>();
        bv.EndTurnButton.targetGraphic = button.GetComponent<Image>();
        bv.EndTurnButton.transition = Selectable.Transition.None;
        // Disabled state: dim the whole button rather than one graphic.
        button.gameObject.AddComponent<CanvasGroup>();
        button.gameObject.AddComponent<ButtonDimmer>();
    }

    static void BuildMessages(BoardView bv, RectTransform board, Fonts f)
    {
        var toast = Node("Message", board);
        Anchor(toast, new Vector2(0.5f, 1), new Vector2(0.5f, 0.5f), new Vector2(0, -269), new Vector2(900, 40));
        Rounded(toast, Palette.Outline.WithAlpha(0.88f), 10);
        bv.MessageText = Text(Stretch("Text", toast, 16, 4, 16, 4), "", f.NunitoBlack, 14, Color.white,
            TextAlignmentOptions.Center);
        bv.MessageText.textWrappingMode = TextWrappingModes.Normal;
        bv.MessageText.enableAutoSizing = true;
        bv.MessageText.fontSizeMin = 10;
        bv.MessageText.fontSizeMax = 14;
    }

    // --- pieces

    static TMP_Text Avatar(RectTransform rt, Color face, Color lip, float radius, float lipHeight, float size, Fonts f)
    {
        Rounded(rt, Palette.Outline, radius);
        Rounded(Stretch("Lip", rt, 3, 3, 3, 3), lip, radius - 3);
        Rounded(Stretch("Face", rt, 3, 3, 3, 3 + lipHeight), face, radius - 3);
        return Text(Stretch("Text", rt, 0, 0, 0, 1), "", f.Lilita, size, Color.white, TextAlignmentOptions.Center,
            f.LilitaOutline);
    }

    /// <summary>A health bar: navy track with 2 px padding; returns the fill, sized by BoardView.</summary>
    static RectTransform Bar(RectTransform track, Color fill, float trackRadius, float fillRadius, float shineHeight)
    {
        Rounded(track, Palette.Outline, trackRadius);
        var size = track.sizeDelta;
        var bar = Box("Fill", track, 2, 2, size.x - 4, size.y - 4);
        Rounded(bar, fill, fillRadius);
        var shine = Node("Shine", bar);
        shine.anchorMin = new Vector2(0, 1);
        shine.anchorMax = new Vector2(1, 1);
        shine.offsetMin = new Vector2(1, -shineHeight);
        shine.offsetMax = new Vector2(-1, 0);
        Rounded(shine, Color.white.WithAlpha(0.35f), Mathf.Min(fillRadius, shineHeight / 2f));
        return bar;
    }

    /// <summary>A right-aligned row: energy gems (a template gem BoardView clones) then a count.</summary>
    static RectTransform GemRow(RectTransform row, Vector2 gemSize, bool shine)
    {
        var rowLayout = row.gameObject.AddComponent<HorizontalLayoutGroup>();
        rowLayout.childAlignment = TextAnchor.MiddleRight;
        rowLayout.spacing = 8;
        rowLayout.childControlWidth = rowLayout.childControlHeight = false;
        rowLayout.childForceExpandWidth = rowLayout.childForceExpandHeight = false;

        var gems = Node("Gems", row);
        var gemsLayout = gems.gameObject.AddComponent<HorizontalLayoutGroup>();
        gemsLayout.childAlignment = TextAnchor.MiddleRight;
        gemsLayout.spacing = 3;
        gemsLayout.childControlWidth = gemsLayout.childControlHeight = false;
        gemsLayout.childForceExpandWidth = gemsLayout.childForceExpandHeight = false;
        var fit = gems.gameObject.AddComponent<ContentSizeFitter>();
        fit.horizontalFit = ContentSizeFitter.FitMode.PreferredSize;
        gems.sizeDelta = new Vector2(0, gemSize.y);

        var gem = Node("Gem", gems);
        gem.sizeDelta = gemSize;
        Img(Stretch("Fill", gem, 0, 0, 0, 0), Sprite("gem_fill"), Palette.Energy);
        Img(Stretch("Rim", gem, 0, 0, 0, 0), Sprite("gem_rim"), Palette.Outline);
        if (shine) Img(Stretch("Shine", gem, 0, 0, 0, 0), Sprite("gem_shine"), Color.white.WithAlpha(0.6f));
        return gems;
    }

    static TMP_Text Number(RectTransform rt, Fonts f, float size) =>
        Text(rt, "0", f.Lilita, size, Color.white, TextAlignmentOptions.Center, f.LilitaOutline);

    // --- layout helpers: the shared ones in Tcg.View.Ui

    static RectTransform Node(string name, Transform parent) => Ui.Node(name, parent);

    static RectTransform Box(string name, Transform parent, float x, float y, float w, float h, bool bottom = false) =>
        Ui.Box(name, parent, x, y, w, h, bottom);

    static RectTransform Stretch(string name, Transform parent, float left, float top, float right, float bottom) =>
        Ui.Stretch(name, parent, left, top, right, bottom);

    static void Anchor(RectTransform rt, Vector2 anchor, Vector2 pivot, Vector2 position, Vector2 size) =>
        Ui.Anchor(rt, anchor, pivot, position, size);

    static Image Img(RectTransform rt, Sprite sprite, Color colour) => Ui.Img(rt, sprite, colour);

    static Image Rounded(RectTransform rt, Color colour, float radius) => Ui.Rounded(rt, colour, radius);

    static TextMeshProUGUI Text(RectTransform rt, string text, TMP_FontAsset font, float size, Color colour,
        TextAlignmentOptions align, Material material = null) => Ui.Text(rt, text, font, size, colour, align, material);
}
