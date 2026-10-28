using System.Collections.Generic;
using System.Text;
using Tcg.Protocol;

namespace Tcg.View
{
    /// <summary>
    /// Builds a card's text box from the server's data (docs/client-design.md, "The card"):
    /// keywords first in bold ("Guard.", "Duelist +2."), then one paragraph per ability line with
    /// its lead-in bold, and choose-one options on their own lines. Every word comes from the server.
    /// </summary>
    public static class CardText
    {
        const string Granted = "#2F8A27";  // a keyword an ability gave this card: green, like a raised stat

        /// <summary>Keyword names and rules from card_set, by key.</summary>
        public static IReadOnlyDictionary<string, KeywordInfo> Keywords = new Dictionary<string, KeywordInfo>();

        /// <summary>Aspect (class) names and descriptions from card_set, by aspect ID and "neutral".</summary>
        public static IReadOnlyDictionary<string, AspectInfo> Aspects = new Dictionary<string, AspectInfo>();

        public static string Build(CardDef def, CardInstance instance)
        {
            var sb = new StringBuilder();
            var keywords = instance?.keywords ?? def.keywords;
            if (keywords != null)
                foreach (var kv in keywords)
                {
                    int value = KeywordValues.Of(keywords, kv.Key);
                    if (value <= 0) continue;
                    bool granted = KeywordValues.Of(def.keywords, kv.Key) < value;
                    string word = $"<b>{KeywordLabel(kv.Key, value)}.</b> ";
                    sb.Append(granted ? $"<color={Granted}>{word}</color>" : word);
                }
            if (def.ability_text != null)
                foreach (var line in def.ability_text)
                {
                    if (sb.Length > 0) sb.Append('\n');
                    sb.Append(Ability(line));
                }
            return sb.ToString().TrimEnd();
        }

        /// <summary>"Guard", "Duelist +2", with the server's name for the keyword.</summary>
        public static string KeywordLabel(string key, int value)
        {
            string name = Keywords.TryGetValue(key, out var info) ? info.name : key;
            return info != null && info.numbered ? $"{name} +{value}" : name;
        }

        /// <summary>The keyword's reminder text, with N replaced by its number.</summary>
        public static string KeywordRule(string key, int value) =>
            Keywords.TryGetValue(key, out var info) ? info.rule.Replace("+N", $"+{value}").Replace(" N ", $" {value} ") : "";

        /// <summary>One ability line, its lead-in bold and choose-one options on their own lines.</summary>
        public static string Ability(string line)
        {
            var (lead, rest) = SplitLeadIn(line);
            string body = rest.Replace(" • ", "\n• ");
            return lead.Length > 0 ? $"<b>{lead}</b>{body}" : body;
        }

        /// <summary>
        /// Splits off the lead-in: a trigger up to its first comma ("When you play this unit,").
        /// Otherwise none.
        /// </summary>
        public static (string lead, string rest) SplitLeadIn(string line)
        {
            int cut = -1;
            if (line.StartsWith("When ") || line.StartsWith("Whenever ") || line.StartsWith("At "))
                cut = line.IndexOf(',');
            return cut < 0 ? ("", line) : (line.Substring(0, cut + 1), line.Substring(cut + 1));
        }
    }
}
