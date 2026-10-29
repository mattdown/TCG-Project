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
    const string PaintedDir = "Assets/Art/Sprites";
    const string FontDir = "Assets/Fonts";
    const string PrefabPath = "Assets/Prefabs/Card.prefab";
    const string ScenePath = "Assets/Scenes/Main.unity";
    const float SpritePpu = 400f;   // 4 texture px per canvas unit
    const float SliceRadius = 16f;  // corner radius baked into rounded.png
    const string Charset =
        " !\"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~·…’→❄−•✕";
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

        // Painted art (card frames, the arena): large and shown much smaller, so mipmapped.
        foreach (var guid in AssetDatabase.FindAssets("t:Texture2D", new[] { PaintedDir }))
        {
            var ti = (TextureImporter)AssetImporter.GetAtPath(AssetDatabase.GUIDToAssetPath(guid));
            ti.textureType = TextureImporterType.Sprite;
            ti.spriteImportMode = SpriteImportMode.Single;
            ti.mipmapEnabled = true;
            ti.alphaIsTransparency = true;
            ti.maxTextureSize = 4096;
            ti.textureCompression = TextureImporterCompression.CompressedHQ;
            ti.filterMode = FilterMode.Trilinear;
            ti.wrapMode = TextureWrapMode.Clamp;
            var settings = new TextureImporterSettings();
            ti.ReadTextureSettings(settings);
            settings.spriteMeshType = SpriteMeshType.FullRect;
            ti.SetTextureSettings(settings);
            ti.SaveAndReimport();
        }
    }

    static Sprite ArtSprite(string file) => AssetDatabase.LoadAssetAtPath<Sprite>($"{PaintedDir}/{file}");

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

        // Lilita One and Nunito lack some symbols, such as → (previews): fall back to DejaVu Sans.
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
        m.EnableKeyword(ShaderUtilities.Keyword_Outline);
        m.SetFloat(ShaderUtilities.ID_OutlineWidth, 0.349f);
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
        // Sized to the painted frame, which pokes out further at the top and bottom than at the sides.
        cv.GlowHalo = Img(Stretch("GlowHalo", visual, -24.35f, -27.78f, -27.46f, -31.25f), _glow, Color.white);
        cv.GlowHalo.type = Image.Type.Sliced;
        cv.GlowHalo.gameObject.SetActive(false);
        cv.TargetOutline = Ui.Outline(Stretch("TargetRing", visual, 0, -4.63f, -3, -8.5f), Palette.GlowTarget, 16);
        cv.TargetOutline.gameObject.SetActive(false);
        Img(Stretch("Body", visual, 0, 0, 0, 0), null, Color.clear).raycastTarget = true;  // taps and drags

        // The frame art's own outline as the drop shadow.
        cv.UnitFrame = ArtSprite("card_frame.png");
        cv.ActionFrame = ArtSprite("card_frame_action.png");
        var shadow = FrameBox("Shadow", visual, 0, 0, FramePx.x, FramePx.y);
        shadow.anchoredPosition += new Vector2(0, -4);
        cv.FrameShadow = Img(shadow, cv.UnitFrame, Palette.CardShadow.WithAlpha(0.5f));

        // The art sits behind the frame, clipped to the oval window's bounds (the frame hides the corners).
        // A stencil Mask, not RectMask2D: that clips to a screen-aligned rect, so it breaks on the tilted hand.
        var window = FrameBox("ArtWindow", visual, 264, 218, 856, 862);
        Img(window, null, Color.white);
        window.gameObject.AddComponent<Mask>().showMaskGraphic = false;
        var artSprites = new List<Sprite>();
        for (int a = 1; a <= 6; a++)
            foreach (var n in ArtNames) artSprites.Add(Sprite($"art_{a}_{n}"));
        cv.ArtSprites = artSprites.ToArray();
        var artBox = Node("Art", window);
        float artHeight = 862 * FrameScale;
        Anchor(artBox, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), Vector2.zero, new Vector2(artHeight * 1.5f, artHeight));
        cv.Art = Img(artBox, artSprites[2], Color.white);

        // A unit that has attacked: the art just dims (the glow on units that can attack does the rest).
        var attacked = Stretch("Attacked", window, 0, 0, 0, 0);
        Img(attacked, null, Palette.Attacked);
        cv.AttackedOverlay = attacked.gameObject;
        attacked.gameObject.SetActive(false);

        // Frozen: ice over the art. Hidden (Elusive, not attacked yet): a misty veil.
        var frozen = Stretch("Frozen", window, 0, 0, 0, 0);
        Img(frozen, null, Palette.Hex("#BDEBFF").WithAlpha(0.55f));
        Text(Stretch("Flake", frozen, 0, 0, 0, 0), "❄", f.Lilita, 34, Palette.Hex("#F2FBFF"),
            TextAlignmentOptions.Center, f.LilitaOutline);
        cv.FrozenOverlay = frozen.gameObject;
        frozen.gameObject.SetActive(false);
        var hidden = Stretch("Hidden", window, 0, 0, 0, 0);
        Img(hidden, null, Palette.Hex("#C9C2F2").WithAlpha(0.45f));
        cv.HiddenOverlay = hidden.gameObject;
        hidden.gameObject.SetActive(false);

        cv.Frame = Img(FrameBox("Frame", visual, 0, 0, FramePx.x, FramePx.y), cv.UnitFrame, Color.white);

        // The name on the wooden banner; the subtitle on the tab under it.
        cv.NameText = Text(FrameBox("Name", visual, 215, 1092, 940, 150), "Card name", f.Lilita, 13, Color.white,
            TextAlignmentOptions.Center, f.LilitaOutline);
        cv.NameText.enableAutoSizing = true;
        cv.NameText.fontSizeMin = 8;
        cv.NameText.fontSizeMax = 13;
        cv.SubtitleText = Text(FrameBox("Subtitle", visual, 440, 1268, 485, 90), "", f.NunitoItalic, 8.5f,
            Palette.ParchmentText, TextAlignmentOptions.Center);
        cv.SubtitleText.enableAutoSizing = true;
        cv.SubtitleText.fontSizeMin = 5f;
        cv.SubtitleText.fontSizeMax = 8.5f;

        // The parchment, kept clear of the power orb and the shield in its bottom corners.
        cv.BodyText = Text(FrameBox("Text", visual, 250, 1385, 870, 380), "", f.Nunito, 10, Palette.ParchmentText,
            TextAlignmentOptions.Center);
        cv.BodyText.textWrappingMode = TextWrappingModes.Normal;
        cv.BodyText.lineSpacing = -12f;
        cv.BodyText.enableAutoSizing = true;
        cv.BodyText.fontSizeMin = 5;
        cv.BodyText.fontSizeMax = 10;

        // The job tag on the bottom edge, its rim in the aspect colour.
        var tag = Node("Traits", visual);
        Anchor(tag, new Vector2(0.5f, 0), new Vector2(0.5f, 0), new Vector2(0, 0), new Vector2(0, 12));
        cv.AspectTag = Rounded(tag, Palette.Aspect(1), 6);
        var tagFill = Rounded(Stretch("Fill", tag, 1.5f, 1.5f, 1.5f, 1.5f), Palette.CardNavy, 5);
        tagFill.gameObject.AddComponent<LayoutElement>().ignoreLayout = true;
        var tagLayout = tag.gameObject.AddComponent<HorizontalLayoutGroup>();
        tagLayout.padding = new RectOffset(8, 8, 0, 0);
        tagLayout.childControlWidth = tagLayout.childControlHeight = true;
        tagLayout.childForceExpandWidth = false;
        tagLayout.childForceExpandHeight = true;
        tag.gameObject.AddComponent<ContentSizeFitter>().horizontalFit = ContentSizeFitter.FitMode.PreferredSize;
        cv.TraitText = Text(Node("Text", tag), "Unit", f.NunitoBlack, 9, Palette.TraitText, TextAlignmentOptions.Center);
        cv.TraitText.margin = new Vector4(0, 0, 0, 1);
        cv.TraitText.characterSpacing = 4f;
        cv.TraitTag = tag;

        // The numbers sit on the frame's own gem (cost), orb (power) and shield (health).
        var cost = FrameBox("Cost", visual, 125, 160, 200, 200);
        cv.CostText = Number(Stretch("Value", cost, 0, 3.3f, 0, -2.3f), f, 20);
        cv.CostGem = cost;

        var power = FrameBox("Power", visual, 125, 1720, 180, 180);
        cv.PowerText = Number(Stretch("Value", power, 0, 0.5f, 0, 0.5f), f, 18);
        var health = FrameBox("Health", visual, 1085, 1712, 175, 175);
        cv.HealthText = Number(Stretch("Value", health, 0, 4.34f, 0, -1.34f), f, 18);
        cv.PowerIcon = power;
        cv.HealthIcon = health;
        cv.UnitOnly = new[] { power.gameObject, health.gameObject };

        System.IO.Directory.CreateDirectory("Assets/Prefabs");
        var prefab = PrefabUtility.SaveAsPrefabAsset(root, PrefabPath);
        Object.DestroyImmediate(root);
        return prefab.GetComponent<CardView>();
    }

    // The frame art (Art/Sprites/card_frame*.png, 1342x2000) in card units: its wood and parchment
    // fill the 150x210 card, and the cost gem pokes out at the top left.
    static readonly Vector2 FramePx = new(1342, 2000);
    const float FrameScale = 0.1127f;
    static readonly Vector2 FrameOrigin = new(-0.6f, -10.9f);

    /// <summary>A box placed in frame-art pixels (y down from the art's top-left).</summary>
    static RectTransform FrameBox(string name, Transform card, float x, float y, float w, float h) =>
        Box(name, card, FrameOrigin.x + x * FrameScale, FrameOrigin.y + y * FrameScale, w * FrameScale, h * FrameScale);

    // --- the board

    const float DividerY = 270f;  // between the unit rows (centres 160.5 and 380.5 down)

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
        bv.ManaFull = ArtSprite("mana_full.png");
        bv.ManaEmpty = ArtSprite("mana_empty.png");

        // The forest arena, its centre line on the divider between the two rows of units.
        var arena = Node("Background", board);
        Img(arena, ArtSprite("game_background.jpeg"), Color.white);
        var fit = arena.gameObject.AddComponent<BackgroundFit>();
        fit.ArtLine = 778f / 1536f;
        fit.BoardLine = DividerY;

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

        // The field: both rows of units either side of the arena's line.
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
        // The enemy hero's painted panel, top left. The whole panel is the attack_hero target.
        bv.OpponentHero = HeroPanel("Opponent", board, ArtSprite("hero_opponent.png"), HeroInset, HeroInset, false, f,
            out bv.OpponentNameText, out bv.OpponentHealthFill, out bv.OpponentHealthText);
        bv.OpponentInfoText = Text(Box("OpponentInfo", board, HeroInset + HeroWidth + 6, HeroInset + 4, 160, 40), "", f.NunitoBlack, 13,
            Palette.SubtleText, TextAlignmentOptions.TopLeft);
        bv.OpponentInfoText.lineSpacing = -8f;

        // The help button takes the top-right corner; the enemy's mana sits to its left.
        var help = Node("Help", board);
        Anchor(help, new Vector2(1, 1), new Vector2(1, 1), new Vector2(-24, -8), new Vector2(44, 44));
        bv.HelpButton = Ui.Button(help, "?", Palette.HumanAccent, Palette.HumanLip, 24, out _, 12);

        var mana = Node("OpponentMana", board);
        Anchor(mana, new Vector2(1, 1), new Vector2(1, 1), new Vector2(-80, -14), new Vector2(400, 22));
        bv.OpponentCrystals = GemRow(mana, new Vector2(20, 22), out var opponentTray);
        bv.OpponentManaText = Number(Node("Count", opponentTray), f, 16);
        bv.OpponentManaText.rectTransform.sizeDelta = new Vector2(46, 22);
        bv.OpponentManaText.gameObject.AddComponent<LayoutElement>().minWidth = 46;
    }

    static void BuildHumanHero(BoardView bv, RectTransform board, Fonts f)
    {
        // Your painted panel, bottom left; the deck count beside it is where drawn cards fly from.
        bv.HumanHero = HeroPanel("Human", board, ArtSprite("hero_you.png"), HeroInset, 720 - HeroInset - HeroHeight, true, f,
            out bv.HumanNameText, out bv.HumanHealthFill, out bv.HumanHealthText);
        bv.HumanInfoText = Text(Box("HumanInfo", board, HeroInset + HeroWidth + 6, 720 - HeroInset - 26, 120, 22, bottom: true), "", f.NunitoBlack, 13,
            Palette.SubtleText, TextAlignmentOptions.BottomLeft);
    }

    // The hero art (Art/Sprites/hero_*.png, 914x1071) and where its banner, bar slot and heart are, in its pixels.
    const float HeroHeight = 185f, HeroInset = 18f;
    const float HeroWidth = HeroHeight * 914f / 1071f;

    /// <summary>
    /// A hero: a red glow behind (the attack target ring), the painted panel with the character,
    /// a health fill in its bar slot (BoardView sizes it), the name on the banner and the health in the heart.
    /// </summary>
    static RectTransform HeroPanel(string who, RectTransform board, Sprite art, float x, float y, bool bottom, Fonts f,
        out TMP_Text name, out RectTransform fill, out TMP_Text health)
    {
        float s = HeroHeight / 1071f;
        var panel = Box(who + "Hero", board, x, y, HeroWidth, HeroHeight, bottom);
        RectTransform At(string part, float px, float py, float pw, float ph) => Box(part, panel, px * s, py * s, pw * s, ph * s);

        // The glow's falloff (50 units) runs deeper than its inset, so only the soft edge shows past the panel.
        var ring = Img(Stretch("TargetRing", panel, -22, -22, -22, -22), _glow, Palette.GlowTarget);
        ring.type = Image.Type.Sliced;
        ring.pixelsPerUnitMultiplier = 0.8f;
        ring.gameObject.SetActive(false);
        Img(Stretch("Art", panel, 0, 0, 0, 0), art, Color.white).raycastTarget = true;

        fill = At("HealthFill", 142, 836, 508, 86);
        Rounded(fill, Palette.Health, 4);
        var shine = Node("Shine", fill);
        shine.anchorMin = new Vector2(0, 1);
        shine.anchorMax = new Vector2(1, 1);
        shine.offsetMin = new Vector2(1, -3);
        shine.offsetMax = new Vector2(-1, -1);
        Rounded(shine, Color.white.WithAlpha(0.35f), 1.5f);

        name = Text(At("Name", 225, 692, 510, 78), "", f.Lilita, 13, Color.white, TextAlignmentOptions.Center, f.LilitaOutline);
        name.enableAutoSizing = true;
        name.fontSizeMin = 7;
        name.fontSizeMax = 13;
        health = Number(At("Health", 677, 812, 140, 112), f, 15);
        return panel;
    }

    static void BuildManaAndButtons(BoardView bv, RectTransform board, Fonts f)
    {
        var mana = Node("HumanMana", board);
        Anchor(mana, new Vector2(1, 0), new Vector2(1, 1), new Vector2(-24, 220), new Vector2(400, 28));
        bv.HumanCrystals = GemRow(mana, new Vector2(26, 29), out var humanTray);
        bv.HumanManaText = Number(Node("Count", humanTray), f, 20);
        bv.HumanManaText.rectTransform.sizeDelta = new Vector2(58, 28);
        bv.HumanManaText.gameObject.AddComponent<LayoutElement>().minWidth = 58;

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

    /// <summary>
    /// A right-aligned row: mana crystals (a template crystal BoardView clones) then a count, in a
    /// tray that sizes to them, over a soft dark glow so the stones stand out from the arena.
    /// The row and the tray size their children to fit (no nested ContentSizeFitters, which miss
    /// the crystals BoardView adds each turn).
    /// </summary>
    static RectTransform GemRow(RectTransform row, Vector2 gemSize, out RectTransform tray)
    {
        var rowLayout = row.gameObject.AddComponent<HorizontalLayoutGroup>();
        rowLayout.childAlignment = TextAnchor.MiddleRight;
        rowLayout.childControlWidth = true;
        rowLayout.childControlHeight = false;
        rowLayout.childForceExpandWidth = rowLayout.childForceExpandHeight = false;

        tray = Node("Tray", row);
        tray.sizeDelta = new Vector2(0, gemSize.y);
        var trayLayout = tray.gameObject.AddComponent<HorizontalLayoutGroup>();
        trayLayout.childAlignment = TextAnchor.MiddleRight;
        trayLayout.spacing = 8;
        trayLayout.childControlWidth = true;
        trayLayout.childControlHeight = false;
        trayLayout.childForceExpandWidth = trayLayout.childForceExpandHeight = false;

        float spread = gemSize.y * 0.9f;
        var shadow = Img(Stretch("Shadow", tray, -spread, -spread * 1.2f, -spread, -spread * 1.2f),
            _glow, Color.black.WithAlpha(0.85f));
        shadow.type = Image.Type.Sliced;
        shadow.pixelsPerUnitMultiplier = 40f / spread;  // the glow's 40-unit falloff scaled to the spread
        shadow.raycastTarget = false;
        shadow.gameObject.AddComponent<LayoutElement>().ignoreLayout = true;

        var gems = Node("Gems", tray);
        var gemsLayout = gems.gameObject.AddComponent<HorizontalLayoutGroup>();
        gemsLayout.childAlignment = TextAnchor.MiddleRight;
        gemsLayout.spacing = 3;
        gemsLayout.childControlWidth = gemsLayout.childControlHeight = false;
        gemsLayout.childForceExpandWidth = gemsLayout.childForceExpandHeight = false;
        gems.sizeDelta = new Vector2(0, gemSize.y);

        // A painted crystal (BoardView swaps full / empty), over a gold glow shown on the ones a play would spend.
        var gem = Node("Gem", gems);
        gem.sizeDelta = gemSize;
        var spend = Img(Stretch("Spend", gem, -gemSize.x * 0.25f, -gemSize.y * 0.25f, -gemSize.x * 0.25f, -gemSize.y * 0.25f),
            Ui.Theme.Dot, Palette.GlowSelected.WithAlpha(0.85f));
        spend.gameObject.SetActive(false);
        Img(Stretch("Crystal", gem, 0, 0, 0, 0), ArtSprite("mana_full.png"), Color.white);
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
