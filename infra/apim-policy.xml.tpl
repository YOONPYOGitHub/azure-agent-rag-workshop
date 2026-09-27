<!-- Dedicated API: intentionally no base inheritance, no body tracing/logging.
     The provisioner separately refuses unsafe APIM diagnostic configurations. -->
<policies>
  <inbound>
    <choose>
      <when condition="{{DENY_ROUTE}}">
        <return-response><set-status code="403" reason="Forbidden" /><set-body>Workshop route or index denied.</set-body></return-response>
      </when>
    </choose>
    <rate-limit calls="60" renewal-period="60" />
    <choose>
      <when condition="@(context.Request.Body != null &amp;&amp; System.Text.Encoding.UTF8.GetByteCount(context.Request.Body.As&lt;string&gt;(preserveContent: true)) &gt; ((context.Operation.Id == &quot;responses&quot; || context.Operation.Id == &quot;embeddings&quot;) ? 262144 : 2097152))">
        <return-response><set-status code="413" reason="Payload Too Large" /></return-response>
      </when>
    </choose>
    <set-header name="Authorization" exists-action="delete" />
    <set-header name="api-key" exists-action="delete" />
    <set-header name="Ocp-Apim-Subscription-Key" exists-action="delete" />
    <set-header name="Ocp-Apim-Trace" exists-action="delete" />
    <set-header name="Apim-Debug-Authorization" exists-action="delete" />
    <set-query-parameter name="subscription-key" exists-action="delete" />
    <set-query-parameter name="api-key" exists-action="delete" />
    <choose>
      <when condition='@(context.Operation.Id == "responses" || context.Operation.Id == "embeddings")'>
        <set-body><![CDATA[@{
          var b = context.Request.Body.As<JObject>();
          var embedding = context.Operation.Id == "embeddings";
          var allowed = embedding ? new [] {"model", "input", "dimensions", "encoding_format", "user"} : new [] {"model", "input", "instructions", "tools", "tool_choice", "parallel_tool_calls", "max_output_tokens", "temperature", "top_p", "stream", "text", "reasoning", "store", "metadata", "user", "include"};
          // Explicitly disallow previous_response_id/conversation and every unknown root field.
          if (b.Properties().Any(p => !allowed.Contains(p.Name))) { throw new Exception("Invalid fields"); }
          if ((string)b["model"] != (embedding ? "text-embedding-3-small" : "gpt-5.6-terra")) { throw new Exception("Invalid model"); }
          var input = b["input"];
          if (input == null || input.Type == JTokenType.Null || input.ToString().Length == 0 || input.ToString().Length > 24000) { throw new Exception("Invalid input"); }
          if (embedding) {
            if (input.Type != JTokenType.String && input.Type != JTokenType.Array) { throw new Exception("Text input required"); }
            if (input.Type == JTokenType.Array && (input.Count() == 0 || input.Count() > 16 || input.Any(x => x.Type != JTokenType.String || x.ToString().Length == 0))) { throw new Exception("Invalid batch"); }
            if (b["dimensions"] != null && (b["dimensions"].Type != JTokenType.Integer || (int)b["dimensions"] != 1536)) { throw new Exception("Invalid dimensions"); }
            b["dimensions"] = 1536;
          } else {
            if (b["include"] != null && (b["include"].Type != JTokenType.Array || b["include"].Count() > 1 || b["include"].Any(x => (string)x != "reasoning.encrypted_content"))) { throw new Exception("Only stateless reasoning include allowed"); }
            if (input.Type != JTokenType.String && input.Type != JTokenType.Array) { throw new Exception("Invalid input"); }
            if (input.Type == JTokenType.Array) {
              if (input.Count() == 0 || input.Count() > 100) { throw new Exception("Invalid messages"); }
              foreach (var item in input) {
                if (item.Type != JTokenType.Object) { throw new Exception("Invalid item"); }
                var type = (string)item["type"] ?? "message";
                if (type == "message") {
                  if (((JObject)item).Properties().Any(p => !new [] {"type", "role", "content"}.Contains(p.Name))) { throw new Exception("Invalid message fields"); }
                  if (!new [] {"user", "assistant", "system", "developer"}.Contains((string)item["role"])) { throw new Exception("Invalid role"); }
                  var content = item["content"];
                  if (content == null || (content.Type != JTokenType.String && content.Type != JTokenType.Array)) { throw new Exception("Invalid content"); }
                  if (content.Type == JTokenType.Array) {
                    foreach (var part in content) {
                      if (part.Type != JTokenType.Object || !new [] {"input_text", "output_text"}.Contains((string)part["type"]) || part["text"] == null || part["text"].Type != JTokenType.String || ((JObject)part).Properties().Any(p => !new [] {"type", "text", "annotations", "logprobs"}.Contains(p.Name))) { throw new Exception("Only text content allowed"); }
                    }
                  }
                } else if (type == "function_call") {
                  if (((JObject)item).Properties().Any(p => !new [] {"type", "id", "call_id", "name", "arguments", "status"}.Contains(p.Name))) { throw new Exception("Invalid function call"); }
                } else if (type == "function_call_output") {
                  if (((JObject)item).Properties().Any(p => !new [] {"type", "call_id", "output", "status"}.Contains(p.Name)) || item["output"] == null || item["output"].Type != JTokenType.String) { throw new Exception("Invalid function output"); }
                } else if (type == "reasoning") {
                  if (((JObject)item).Properties().Any(p => !new [] {"type", "id", "summary", "encrypted_content", "status"}.Contains(p.Name)) || item["encrypted_content"] == null || item["encrypted_content"].Type != JTokenType.String || item["encrypted_content"].ToString().Length == 0 || item["summary"] == null || item["summary"].Type != JTokenType.Array) { throw new Exception("Inline encrypted reasoning required"); }
                } else { throw new Exception("Hosted or referenced items forbidden"); }
              }
            }
            if (b["instructions"] != null && (b["instructions"].Type != JTokenType.String || b["instructions"].ToString().Length > 12000)) { throw new Exception("Invalid instructions"); }
            var tools = b["tools"];
            if (tools != null && (tools.Type != JTokenType.Array || tools.Count() > 16 || tools.Any(t => t.Type != JTokenType.Object || (string)t["type"] != "function" || ((JObject)t).Properties().Any(p => !new [] {"type", "name", "description", "parameters", "strict"}.Contains(p.Name))))) { throw new Exception("Only function tools allowed"); }
            var choice = b["tool_choice"];
            if (choice != null && !((choice.Type == JTokenType.String && new [] {"auto", "none", "required"}.Contains((string)choice)) || (choice.Type == JTokenType.Object && (string)choice["type"] == "function" && !((JObject)choice).Properties().Any(p => !new [] {"type", "name"}.Contains(p.Name))))) { throw new Exception("Invalid tool choice"); }
            if (b["max_output_tokens"] != null && (b["max_output_tokens"].Type != JTokenType.Integer || (int)b["max_output_tokens"] < 1 || (int)b["max_output_tokens"] > 1500)) { throw new Exception("Invalid output bound"); }
            b["max_output_tokens"] = b["max_output_tokens"] ?? new JValue(1500);
            b["store"] = false;
          }
          return b.ToString(Newtonsoft.Json.Formatting.None);
        }]]></set-body>
        <set-backend-service base-url="{{FOUNDRY_ENDPOINT}}" />
        <rewrite-uri template='@("/openai/v1/" + context.Operation.Id)' copy-unmatched-params="false" />
        <authentication-managed-identity resource="https://cognitiveservices.azure.com" />
      </when>
      <otherwise>
        <choose>
          <when condition='@(context.Request.Method == "PUT" || context.Request.Method == "POST")'>
            <set-body><![CDATA[@{
              var b = context.Request.Body.As<JObject>();
              if (context.Request.Method == "PUT") {
                if ((string)b["name"] != context.Subscription.Name) { throw new Exception("Index name mismatch"); }
                if (b["encryptionKey"] != null || (b["vectorSearch"] != null && b["vectorSearch"]["vectorizers"] != null && b["vectorSearch"]["vectorizers"].HasValues)) { throw new Exception("External services forbidden"); }
              } else if (context.Operation.Id.EndsWith("search-docs")) {
                if (b["top"] != null && (b["top"].Type != JTokenType.Integer || (int)b["top"] < 1 || (int)b["top"] > 20)) { throw new Exception("Invalid top"); }
                b["top"] = b["top"] ?? new JValue(5);
                if (b["vectorQueries"] != null && b["vectorQueries"].Any(q => (string)q["kind"] != "vector")) { throw new Exception("Only local vectors allowed"); }
              } else {
                if (b["value"] == null || b["value"].Type != JTokenType.Array || b["value"].Count() > 100) { throw new Exception("Invalid document batch"); }
              }
              return b.ToString(Newtonsoft.Json.Formatting.None);
            }]]></set-body>
          </when>
        </choose>
        <set-backend-service base-url="{{SEARCH_ENDPOINT}}" />
        <rewrite-uri template='@(context.Request.OriginalUrl.Path.Substring("/agent-rag/search".Length))' copy-unmatched-params="false" />
        <set-query-parameter name="api-version" exists-action="override"><value>2025-09-01</value></set-query-parameter>
        <authentication-managed-identity resource="https://search.azure.com" />
      </otherwise>
    </choose>
  </inbound>
  <backend><forward-request timeout="120" buffer-response="false" /></backend>
  <outbound>
    <set-header name="Ocp-Apim-Subscription-Key" exists-action="delete" />
  </outbound>
  <on-error>
    <choose>
      <when condition='@(context.LastError.Reason == "OperationNotFound")'>
        <return-response><set-status code="404" reason="Not Found" /><set-body>Workshop route not found.</set-body></return-response>
      </when>
      <when condition='@(context.LastError.Reason == "SubscriptionKeyNotFound" || context.LastError.Reason == "SubscriptionKeyInvalid")'>
        <return-response><set-status code="401" reason="Unauthorized" /><set-body>Valid workshop subscription key required.</set-body></return-response>
      </when>
      <when condition='@(context.LastError.Reason == "RateLimitExceeded")'>
        <return-response><set-status code="429" reason="Too Many Requests" /><set-header name="Retry-After" exists-action="override"><value>60</value></set-header><set-body>Wait before retrying.</set-body></return-response>
      </when>
      <otherwise>
        <return-response><set-status code="400" reason="Request Rejected" /><set-body>Request rejected by workshop gateway.</set-body></return-response>
      </otherwise>
    </choose>
  </on-error>
</policies>
