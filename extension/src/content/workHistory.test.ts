import { describe, it, expect } from "vitest";
import {
  classifyExperienceField,
  classifyEducationField,
  rowsToAdd,
} from "./workHistory";

describe("classifyExperienceField", () => {
  it("classifies the common work-history sub-fields", () => {
    expect(classifyExperienceField("Company")).toBe("company");
    expect(classifyExperienceField("Employer name")).toBe("company");
    expect(classifyExperienceField("Job Title")).toBe("title");
    expect(classifyExperienceField("Role")).toBe("title");
    expect(classifyExperienceField("Start date")).toBe("startDate");
    expect(classifyExperienceField("End date")).toBe("endDate");
    expect(classifyExperienceField("Responsibilities")).toBe("description");
    expect(classifyExperienceField("Location")).toBe("location");
  });

  it("prefers end-date over start-date when both words present", () => {
    expect(classifyExperienceField("End date")).toBe("endDate");
  });

  it("returns undefined for unrelated text", () => {
    expect(classifyExperienceField("Favorite color")).toBeUndefined();
  });
});

describe("classifyEducationField", () => {
  it("classifies the common education sub-fields", () => {
    expect(classifyEducationField("University")).toBe("school");
    expect(classifyEducationField("Institution")).toBe("school");
    expect(classifyEducationField("Degree")).toBe("degree");
    expect(classifyEducationField("Field of study")).toBe("field");
    expect(classifyEducationField("Major")).toBe("field");
    expect(classifyEducationField("GPA")).toBe("gpa");
    expect(classifyEducationField("Graduation date")).toBe("endDate");
  });
});

describe("rowsToAdd", () => {
  it("computes how many rows to add, capped", () => {
    expect(rowsToAdd(3, 1)).toBe(2);
    expect(rowsToAdd(1, 1)).toBe(0);
    expect(rowsToAdd(5, 0)).toBe(4); // treat 0 existing as 1 baseline row
    expect(rowsToAdd(20, 1, 10)).toBe(9); // respects max
  });
});
