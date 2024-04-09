CREATE TABLE "papers" (
    "id" SERIAL PRIMARY KEY,
    "url" TEXT,
    "title" TEXT,
    "abstract" TEXT,
    "summary" TEXT,
    "file_path" TEXT
);
CREATE TABLE "tags" (
    "id" SERIAL PRIMARY KEY,
    "name" TEXT
);
CREATE TABLE "extracted_prompt_engineering_tips" (
    "id" SERIAL PRIMARY KEY,
    "paper_id" INTEGER,
    FOREIGN KEY ("paper_id") REFERENCES "papers" ("id")
);
CREATE TABLE "tiktoks" (
    "id" SERIAL PRIMARY KEY,
    "script" TEXT,
    "video_id" TEXT,
    "video_link" TEXT
);
CREATE TABLE "paper_tiktoks" (
    "paper_id" INTEGER,
    "tiktok_id" INTEGER,
    PRIMARY KEY ("paper_id", "tiktok_id"),
    FOREIGN KEY ("paper_id") REFERENCES "papers" ("id"),
    FOREIGN KEY ("tiktok_id") REFERENCES "tiktoks" ("id")
);
CREATE TABLE "paper_tags" (
    "paper_id" INTEGER,
    "tag_id" INTEGER,
    PRIMARY KEY ("paper_id", "tag_id"),
    FOREIGN KEY ("paper_id") REFERENCES "papers" ("id"),
    FOREIGN KEY ("tag_id") REFERENCES "tags" ("id")
);
