/**
 * cte_helper - JSON-based CLI helper for IOWarp CTE operations.
 * Reads JSON commands from stdin, executes CTE operations, writes JSON to stdout.
 * This bypasses the broken nanobind Python extension by using the C++ API directly.
 *
 * Protocol: one JSON object per line on stdin, one JSON response per line on stdout.
 * First output line is a ready message with init status.
 */

#include <wrp_cte/core/content_transfer_engine.h>
#include <wrp_cte/core/core_client.h>
#include <chimaera/chimaera.h>
#include <iostream>
#include <string>
#include <vector>
#include <cstring>

// Simple JSON key extraction (no external dep)
static std::string json_get(const std::string &json, const std::string &key) {
    std::string search = "\"" + key + "\":";
    auto pos = json.find(search);
    if (pos == std::string::npos) return "";
    pos += search.size();
    while (pos < json.size() && (json[pos] == ' ' || json[pos] == '\t')) pos++;
    if (pos >= json.size()) return "";
    if (json[pos] == '"') {
        pos++;
        auto end = json.find('"', pos);
        if (end == std::string::npos) return "";
        return json.substr(pos, end - pos);
    }
    auto end = json.find_first_of(",}]", pos);
    if (end == std::string::npos) end = json.size();
    std::string val = json.substr(pos, end - pos);
    while (!val.empty() && (val.back() == ' ' || val.back() == '\n')) val.pop_back();
    return val;
}

static std::string to_hex(const char* data, size_t len) {
    static const char hex[] = "0123456789abcdef";
    std::string out;
    out.reserve(len * 2);
    for (size_t i = 0; i < len; i++) {
        unsigned char c = static_cast<unsigned char>(data[i]);
        out += hex[c >> 4];
        out += hex[c & 0x0f];
    }
    return out;
}

static std::vector<char> from_hex(const std::string &hex) {
    std::vector<char> out;
    out.reserve(hex.size() / 2);
    for (size_t i = 0; i + 1 < hex.size(); i += 2) {
        unsigned char hi = 0, lo = 0;
        if (hex[i] >= '0' && hex[i] <= '9') hi = hex[i] - '0';
        else if (hex[i] >= 'a' && hex[i] <= 'f') hi = hex[i] - 'a' + 10;
        else if (hex[i] >= 'A' && hex[i] <= 'F') hi = hex[i] - 'A' + 10;
        if (hex[i+1] >= '0' && hex[i+1] <= '9') lo = hex[i+1] - '0';
        else if (hex[i+1] >= 'a' && hex[i+1] <= 'f') lo = hex[i+1] - 'a' + 10;
        else if (hex[i+1] >= 'A' && hex[i+1] <= 'F') lo = hex[i+1] - 'A' + 10;
        out.push_back(static_cast<char>((hi << 4) | lo));
    }
    return out;
}

static std::string escape_json(const std::string &s) {
    std::string out;
    for (char c : s) {
        if (c == '"') out += "\\\"";
        else if (c == '\\') out += "\\\\";
        else if (c == '\n') out += "\\n";
        else if (c == '\t') out += "\\t";
        else out += c;
    }
    return out;
}

static void respond(const std::string &json) {
    std::cout << json << std::endl;
    std::cout.flush();
}

static void respond_ok(const std::string &extra = "") {
    if (extra.empty())
        respond("{\"status\":\"ok\"}");
    else
        respond("{\"status\":\"ok\"," + extra + "}");
}

static void respond_error(const std::string &msg) {
    respond("{\"status\":\"error\",\"message\":\"" + escape_json(msg) + "\"}");
}

int main() {
    // Initialize CTE client (connects to running Chimaera runtime)
    try {
        bool ok = wrp_cte::core::WRP_CTE_CLIENT_INIT();
        if (!ok) {
            respond_error("WRP_CTE_CLIENT_INIT failed");
            return 1;
        }
    } catch (const std::exception &e) {
        respond_error(std::string("Init exception: ") + e.what());
        return 1;
    }

    // Verify storage targets exist (created by compose section)
    std::string init_info;
    try {
        auto client = WRP_CTE_CLIENT;
        auto targets = client->ListTargets(HSHM_DEFAULT_MEM_CTX);
        init_info = "\"targets\":[";
        for (size_t i = 0; i < targets.size(); i++) {
            if (i > 0) init_info += ",";
            init_info += "\"" + escape_json(targets[i]) + "\"";
        }
        init_info += "],\"target_count\":" + std::to_string(targets.size());
    } catch (const std::exception &e) {
        init_info = "\"targets_error\":\"" + escape_json(e.what()) + "\"";
    } catch (...) {
        init_info = "\"targets_error\":\"unknown\"";
    }

    respond("{\"status\":\"ready\"," + init_info + "}");

    // Process commands from stdin
    std::string line;
    while (std::getline(std::cin, line)) {
        if (line.empty() || line[0] == '#') continue;

        std::string cmd = json_get(line, "cmd");

        try {
            if (cmd == "put") {
                std::string tag_name = json_get(line, "tag");
                std::string blob_name = json_get(line, "blob");
                std::string hex_data = json_get(line, "data");

                if (tag_name.empty() || blob_name.empty()) {
                    respond_error("put requires tag and blob");
                    continue;
                }

                auto data = from_hex(hex_data);
                wrp_cte::core::Tag tag(tag_name);
                tag.PutBlob(blob_name, data.data(), data.size());
                respond_ok("\"size\":" + std::to_string(data.size()));

            } else if (cmd == "get") {
                std::string tag_name = json_get(line, "tag");
                std::string blob_name = json_get(line, "blob");

                if (tag_name.empty() || blob_name.empty()) {
                    respond_error("get requires tag and blob");
                    continue;
                }

                wrp_cte::core::Tag tag(tag_name);
                chi::u64 size = tag.GetBlobSize(blob_name);
                if (size == 0) {
                    respond_error("blob not found or empty");
                    continue;
                }

                std::vector<char> buf(size);
                tag.GetBlob(blob_name, buf.data(), size);
                respond_ok("\"size\":" + std::to_string(size) +
                          ",\"data\":\"" + to_hex(buf.data(), size) + "\"");

            } else if (cmd == "get_size") {
                std::string tag_name = json_get(line, "tag");
                std::string blob_name = json_get(line, "blob");

                wrp_cte::core::Tag tag(tag_name);
                chi::u64 size = tag.GetBlobSize(blob_name);
                respond_ok("\"size\":" + std::to_string(size));

            } else if (cmd == "list_blobs") {
                std::string tag_name = json_get(line, "tag");

                wrp_cte::core::Tag tag(tag_name);
                auto blobs = tag.GetContainedBlobs();

                std::string arr = "[";
                for (size_t i = 0; i < blobs.size(); i++) {
                    if (i > 0) arr += ",";
                    arr += "\"" + escape_json(blobs[i]) + "\"";
                }
                arr += "]";
                respond_ok("\"blobs\":" + arr);

            } else if (cmd == "tag_query") {
                std::string pattern = json_get(line, "pattern");
                if (pattern.empty()) pattern = ".*";

                auto client = WRP_CTE_CLIENT;
                auto tags = client->TagQuery(HSHM_DEFAULT_MEM_CTX, pattern);
                std::string arr = "[";
                for (size_t i = 0; i < tags.size(); i++) {
                    if (i > 0) arr += ",";
                    arr += "\"" + escape_json(tags[i]) + "\"";
                }
                arr += "]";
                respond_ok("\"tags\":" + arr);

            } else if (cmd == "del_blob") {
                std::string tag_name = json_get(line, "tag");
                std::string blob_name = json_get(line, "blob");

                auto client = WRP_CTE_CLIENT;
                wrp_cte::core::Tag tag(tag_name);
                client->DelBlob(HSHM_DEFAULT_MEM_CTX, tag.GetTagId(), blob_name);
                respond_ok();

            } else if (cmd == "del_tag") {
                std::string tag_name = json_get(line, "tag");

                auto client = WRP_CTE_CLIENT;
                client->DelTag(HSHM_DEFAULT_MEM_CTX, tag_name);
                respond_ok();

            } else if (cmd == "ping") {
                respond_ok();

            } else if (cmd == "quit" || cmd == "exit") {
                respond_ok();
                break;

            } else {
                respond_error("unknown command: " + cmd);
            }
        } catch (const std::exception &e) {
            respond_error(std::string("exception: ") + e.what());
        } catch (...) {
            respond_error("unknown exception");
        }
    }

    return 0;
}
